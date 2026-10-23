"""
Canvas reaper - deletes idle SageMaker apps so Canvas cannot quietly bill all day.

Why this exists: in June 2026 a Canvas session left running after class cost
$202 of a $218 SageMaker bill (`USE2-Canvas:Session-Hrs`). Canvas keeps billing
after you close the browser tab - you have to delete the app - and it does not
appear anywhere you would look for a running resource, because it is neither an
endpoint nor an instance.

Triggered on a schedule by EventBridge (see canvas_reaper.tf). For every app of
a watched AppType, in every watched region, it deletes the app when EITHER:

  * it has been idle longer than CANVAS_MAX_IDLE_MINUTES, or
  * it has been alive longer than CANVAS_MAX_AGE_MINUTES, regardless of
    activity (the backstop for "I left it open on a second monitor").

Idle is measured from LastUserActivityTimestamp. IMPORTANT: that field comes
from DescribeApp, NOT ListApps - ListApps returns only DomainId,
UserProfileName, SpaceName, AppType, AppName, Status, CreationTime and
ResourceSpec. An earlier version of this reaper read the field off the ListApps
result, where it is always absent, so every app fell back to its creation time
and got deleted an hour after launch whether or not it was in use - which would
kill Canvas mid-demo. Hence the per-app DescribeApp call below.

Env vars (set by Terraform):
    REAPER_REGIONS            comma-separated regions to sweep. Canvas is
                              region-scoped, and the 2026 overrun happened in
                              us-east-2 while the guard watched us-east-1, so
                              sweep every region you ever open Canvas in.
    WATCH_ALL_DOMAINS         "true" to reap across every domain in each region;
                              otherwise only DOMAIN_ID is watched
    DOMAIN_ID                 single domain to watch when WATCH_ALL_DOMAINS != true
    KILL_APP_TYPES            comma-separated AppTypes to reap (e.g. "Canvas")
    CANVAS_MAX_IDLE_MINUTES   idle threshold before deletion
    CANVAS_MAX_AGE_MINUTES    hard age cap regardless of activity (0 disables)
    DRY_RUN                   "true" to log decisions without deleting
"""

import datetime
import os

import boto3


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _minutes_since(ts) -> float:
    if ts is None:
        return float("inf")
    return (_now_utc() - ts).total_seconds() / 60.0


def _regions() -> list:
    raw = os.environ.get("REAPER_REGIONS", "").strip()
    if raw:
        return [r.strip() for r in raw.split(",") if r.strip()]
    # Fall back to the region the Lambda itself runs in.
    return [os.environ.get("AWS_REGION", "us-east-1")]


def _domains_to_watch(sm) -> list:
    """Either every domain in this region, or just the pinned DOMAIN_ID."""
    if os.environ.get("WATCH_ALL_DOMAINS", "").lower() == "true":
        ids = []
        for page in sm.get_paginator("list_domains").paginate():
            ids.extend(d["DomainId"] for d in page.get("Domains", []))
        return ids
    pinned = os.environ.get("DOMAIN_ID", "").strip()
    return [pinned] if pinned else []


def _owner_scope(app: dict) -> dict:
    """Describe/DeleteApp need the owner: UserProfileName for Canvas, else SpaceName."""
    if app.get("UserProfileName"):
        return {"UserProfileName": app["UserProfileName"]}
    if app.get("SpaceName"):
        return {"SpaceName": app["SpaceName"]}
    return {}


def _activity(sm, app: dict, scope: dict):
    """Fetch LastUserActivityTimestamp via DescribeApp (absent from ListApps).

    Returns (idle_minutes, source). If DescribeApp fails or the field is absent
    -- which happens on a freshly started app -- we fall back to CreationTime,
    because erring toward deleting Canvas is the cheap mistake.
    """
    try:
        detail = sm.describe_app(
            DomainId=app["DomainId"],
            AppType=app["AppType"],
            AppName=app["AppName"],
            **scope,
        )
    except Exception as exc:  # noqa: BLE001 - never let one app stop the sweep
        print(f"  WARN DescribeApp failed for {app.get('AppName')}: {exc}")
        return _minutes_since(app.get("CreationTime")), "creation-time (describe failed)"

    last = detail.get("LastUserActivityTimestamp")
    if last is not None:
        return _minutes_since(last), "last-user-activity"
    return _minutes_since(detail.get("CreationTime") or app.get("CreationTime")), "creation-time"


def handler(event, context):
    kill_types = {
        t.strip()
        for t in os.environ.get("KILL_APP_TYPES", "Canvas").split(",")
        if t.strip()
    }
    max_idle = float(os.environ.get("CANVAS_MAX_IDLE_MINUTES", "60"))
    max_age = float(os.environ.get("CANVAS_MAX_AGE_MINUTES", "0"))
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"

    killed, kept, errors = [], [], []

    for region in _regions():
        sm = boto3.client("sagemaker", region_name=region)
        try:
            domains = _domains_to_watch(sm)
        except Exception as exc:  # noqa: BLE001 - e.g. region not enabled
            print(f"[{region}] WARN could not list domains: {exc}")
            errors.append(f"{region}: list_domains: {exc}")
            continue

        if not domains:
            print(f"[{region}] no domains to watch")
            continue

        apps = []
        paginator = sm.get_paginator("list_apps")
        for domain_id in domains:
            try:
                for page in paginator.paginate(DomainIdEquals=domain_id):
                    apps.extend(page.get("Apps", []))
            except Exception as exc:  # noqa: BLE001
                print(f"[{region}] WARN list_apps failed for {domain_id}: {exc}")
                errors.append(f"{region}/{domain_id}: list_apps: {exc}")

        for app in apps:
            app_type = app.get("AppType")
            status = app.get("Status")
            name = app.get("AppName")

            if app_type not in kill_types:
                continue
            # Pending apps are not billing yet and have no activity record; the
            # next sweep will catch them once they reach InService.
            if status in ("Deleting", "Deleted", "Failed", "Pending"):
                continue

            scope = _owner_scope(app)
            if not scope:
                print(f"[{region}] SKIP (no owner scope): {app_type}/{name}")
                continue

            idle, source = _activity(sm, app, scope)
            age = _minutes_since(app.get("CreationTime"))
            tag = (
                f"{region}/{app.get('DomainId')}:{app_type}/{name} "
                f"({status}, idle {idle:.0f}m via {source}, age {age:.0f}m)"
            )

            too_idle = idle >= max_idle
            too_old = max_age > 0 and age >= max_age
            if not (too_idle or too_old):
                kept.append(tag)
                print(f"[{region}] KEEP {tag}")
                continue

            reason = "idle" if too_idle else f"age cap {max_age:.0f}m"
            if dry_run:
                print(f"[{region}] DRY-RUN would delete ({reason}) {tag}")
                killed.append(tag + " [dry-run]")
                continue

            try:
                sm.delete_app(
                    DomainId=app["DomainId"],
                    AppType=app_type,
                    AppName=name,
                    **scope,
                )
                killed.append(tag)
                print(f"[{region}] DELETED ({reason}) {tag}")
            except sm.exceptions.ResourceNotFound:
                pass
            except Exception as exc:  # noqa: BLE001 - log and keep reaping
                print(f"[{region}] ERROR deleting {tag}: {exc}")
                errors.append(f"{tag}: {exc}")

    print(
        f"reaper done: killed={len(killed)} kept={len(kept)} errors={len(errors)} "
        f"regions={','.join(_regions())}"
    )
    return {"killed": killed, "kept": kept, "errors": errors}
