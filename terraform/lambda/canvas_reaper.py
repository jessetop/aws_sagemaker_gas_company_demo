"""
Canvas reaper — deletes idle SageMaker apps so Canvas can't quietly bill $50/day.

Triggered on a schedule by EventBridge (see canvas_reaper.tf). For every app in
the watched domain whose AppType is in KILL_APP_TYPES (default: Canvas), it
deletes the app if it has been idle longer than CANVAS_MAX_IDLE_MINUTES. Idle is
measured from LastUserActivityTimestamp when available, else from CreationTime.

Env vars (set by Terraform):
    WATCH_ALL_DOMAINS         "true" to reap across every domain in the region;
                              otherwise only DOMAIN_ID is watched
    DOMAIN_ID                 single domain to watch when WATCH_ALL_DOMAINS != true
    KILL_APP_TYPES            comma-separated AppTypes to reap (e.g. "Canvas")
    CANVAS_MAX_IDLE_MINUTES   idle threshold before deletion
"""

import datetime
import os

import boto3

sm = boto3.client("sagemaker")


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _idle_minutes(app: dict) -> float:
    """Minutes since last user activity, falling back to creation time."""
    ts = app.get("LastUserActivityTimestamp") or app.get("CreationTime")
    if ts is None:
        # Unknown age -> treat as idle so we err on the side of killing Canvas.
        return float("inf")
    return (_now_utc() - ts).total_seconds() / 60.0


def _domains_to_watch() -> list:
    """Either every domain in the region, or just the pinned DOMAIN_ID."""
    if os.environ.get("WATCH_ALL_DOMAINS", "").lower() == "true":
        ids = []
        for page in sm.get_paginator("list_domains").paginate():
            ids.extend(d["DomainId"] for d in page.get("Domains", []))
        return ids
    return [os.environ["DOMAIN_ID"]]


def handler(event, context):
    kill_types = {t.strip() for t in os.environ.get("KILL_APP_TYPES", "Canvas").split(",") if t.strip()}
    max_idle = float(os.environ.get("CANVAS_MAX_IDLE_MINUTES", "60"))

    killed, kept = [], []
    paginator = sm.get_paginator("list_apps")

    # Collect apps across every watched domain (each app carries its own DomainId).
    apps = []
    for domain_id in _domains_to_watch():
        for page in paginator.paginate(DomainIdEquals=domain_id):
            apps.extend(page.get("Apps", []))

    for app in apps:
        app_type = app.get("AppType")
        status = app.get("Status")
        name = app.get("AppName")

        if app_type not in kill_types:
            continue
        if status in ("Deleting", "Deleted", "Failed", "Pending"):
            continue

        idle = _idle_minutes(app)
        tag = f"{app.get('DomainId')}:{app_type}/{name} ({status}, idle {idle:.0f}m)"
        if idle < max_idle:
            kept.append(tag)
            continue

        # DeleteApp needs the owner scope: UserProfileName for Canvas, else SpaceName.
        delete_kwargs = {
            "DomainId": app.get("DomainId"),
            "AppType": app_type,
            "AppName": name,
        }
        if app.get("UserProfileName"):
            delete_kwargs["UserProfileName"] = app["UserProfileName"]
        elif app.get("SpaceName"):
            delete_kwargs["SpaceName"] = app["SpaceName"]
        else:
            print(f"SKIP (no owner scope): {tag}")
            continue

        try:
            sm.delete_app(**delete_kwargs)
            killed.append(tag)
            print(f"DELETED {tag}")
        except sm.exceptions.ResourceNotFound:
            pass
        except Exception as exc:  # noqa: BLE001 - log and continue reaping
            print(f"ERROR deleting {tag}: {exc}")

    print(f"reaper done: killed={len(killed)} kept={len(kept)}")
    return {"killed": killed, "kept": kept}
