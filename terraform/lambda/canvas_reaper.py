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
    CANVAS_MAX_IDLE_MINUTES   idle threshold for Canvas apps
    CANVAS_MAX_AGE_MINUTES    hard age cap for Canvas regardless of activity (0 off)
    IDLE_MINUTES_BY_TYPE      per-AppType overrides, e.g. "JupyterLab=30,CodeEditor=30".
                              SageMaker's own native idle shutdown has a hard
                              floor of 60 minutes, so anything tighter than that
                              has to come from here.
    MAX_AGE_MINUTES_BY_TYPE   per-AppType hard age caps, same syntax
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


def _by_type(var: str) -> dict:
    """Parse "JupyterLab=30,CodeEditor=45" into {"JupyterLab": 30.0, ...}."""
    out = {}
    for part in os.environ.get(var, "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        try:
            out[k.strip()] = float(v.strip())
        except ValueError:
            print(f"  WARN ignoring unparseable {var} entry: {part!r}")
    return out


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
    # Canvas keeps its own vars for backwards compatibility; everything else
    # comes from the per-type maps, falling back to the Canvas numbers.
    default_idle = float(os.environ.get("CANVAS_MAX_IDLE_MINUTES", "60"))
    default_age = float(os.environ.get("CANVAS_MAX_AGE_MINUTES", "0"))
    idle_by_type = _by_type("IDLE_MINUTES_BY_TYPE")
    age_by_type = _by_type("MAX_AGE_MINUTES_BY_TYPE")
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    print(f"thresholds: default idle={default_idle:.0f}m age={default_age:.0f}m"
          f" | per-type idle={idle_by_type or '{}'} age={age_by_type or '{}'}")

    killed, kept, skipped, errors = [], [], [], []

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

        # Always say what was inspected, even when the answer is nothing. A cost
        # guard that logs only when it acts is indistinguishable from a cost
        # guard that silently is not running, and the whole point of this thing
        # is to be trusted between classes.
        watched = [a for a in apps if a.get("AppType") in kill_types]
        print(
            f"[{region}] swept {len(domains)} domain(s), {len(apps)} app(s), "
            f"{len(watched)} of type {sorted(kill_types)}"
        )

        for app in apps:
            app_type = app.get("AppType")
            status = app.get("Status")
            name = app.get("AppName")

            if app_type not in kill_types:
                continue
            # Pending apps are not billing yet and have no activity record;
            # Deleting/Deleted/Failed are already on their way out. The next
            # sweep catches anything that reaches InService.
            #
            # These used to be skipped silently, which meant the summary line
            # did not reconcile -- "2 apps watched, killed=1 kept=0" leaves you
            # wondering what happened to the second one. A cost guard you cannot
            # audit is a cost guard you will not trust.
            if status in ("Deleting", "Deleted", "Failed", "Pending"):
                skipped.append(f"{region}/{app_type}/{name} [{status}]")
                print(f"[{region}] SKIP {app_type}/{name} [{status}] - transitioning")
                continue

            scope = _owner_scope(app)
            if not scope:
                skipped.append(f"{region}/{app_type}/{name} [no owner scope]")
                print(f"[{region}] SKIP (no owner scope): {app_type}/{name}")
                continue

            idle, source = _activity(sm, app, scope)
            age = _minutes_since(app.get("CreationTime"))
            max_idle = idle_by_type.get(app_type, default_idle)
            max_age = age_by_type.get(app_type, default_age)
            tag = (
                f"{region}/{app.get('DomainId')}:{app_type}/{name} "
                f"({status}, idle {idle:.0f}/{max_idle:.0f}m via {source}, "
                f"age {age:.0f}m)"
            )

            too_idle = idle >= max_idle
            too_old = max_age > 0 and age >= max_age
            # Deleting a JupyterLab app kills the kernel: files on the space
            # volume survive, in-memory state does not. That is acceptable when
            # the app is genuinely IDLE, which is what we are measuring.
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

    # Counts must reconcile against what was swept, or the log cannot be audited.
    print(
        f"reaper done: killed={len(killed)} kept={len(kept)} "
        f"skipped={len(skipped)} errors={len(errors)} "
        f"regions={','.join(_regions())}"
    )
    return {"killed": killed, "kept": kept, "skipped": skipped, "errors": errors}
