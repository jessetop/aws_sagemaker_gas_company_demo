"""
Verify nothing billable is left running. Read-only; changes nothing.

Run this after any teardown, and before closing the laptop on a class day.

Why this is Python rather than more shell: the shell sweeps call the AWS CLI,
and the CLI on the authoring machine (2.15.47) has no
`sagemaker list-mlflow-tracking-servers` at all. That check therefore failed
silently and could never have reported an MLflow tracking server -- which costs
real money -- while still printing a reassuring "nothing billable found". boto3
in the project venv (1.43+) supports every call used here, so this version has
no CLI-version dependency and cannot quietly skip a check.

The rule it enforces: a check that cannot run is reported as UNKNOWN and exits
non-zero. Silence is never treated as success. That distinction is the whole
point -- a $202 Canvas session in June 2026 was invisible precisely because
nothing said anything.

Usage:
    python cleanup/verify_teardown.py
    python cleanup/verify_teardown.py --regions us-east-1,us-east-2,us-west-2

Exit codes:
    0  nothing billable found, and every check ran
    1  something is still running, or a check could not be completed
"""

import argparse
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args

# Canvas is region-scoped and the June 2026 overrun happened in a region nobody
# was watching, so sweep both regions this project has ever used by default.
DEFAULT_REGIONS = "us-east-1,us-east-2"


class Findings:
    def __init__(self) -> None:
        self.billable: list[str] = []
        self.unknown: list[str] = []

    def found(self, region: str, kind: str, detail: str) -> None:
        self.billable.append(f"[{region}] {kind}: {detail}")

    def cannot_check(self, region: str, kind: str, why: str) -> None:
        self.unknown.append(f"[{region}] {kind}: {why}")


def _check(findings, region, kind, fn):
    """Run one check, classifying any failure as UNKNOWN rather than as a pass."""
    try:
        hits = fn()
    except (ClientError, BotoCoreError, AttributeError) as exc:
        # AttributeError catches an API this boto3 is too old to know about.
        findings.cannot_check(region, kind, f"{type(exc).__name__}: {exc}")
        return
    for h in hits:
        findings.found(region, kind, h)
    print(f"  [{region}] {kind}: {len(hits) if hits else 'none'}")


def sweep_region(findings: Findings, session, region: str) -> None:
    print(f"\n-- {region} --")
    sm = session.client("sagemaker", region_name=region)
    emr = session.client("emr-serverless", region_name=region)

    # Real-time endpoints bill per instance-hour for as long as they exist.
    _check(findings, region, "sagemaker endpoints", lambda: [
        e["EndpointName"]
        for p in sm.get_paginator("list_endpoints").paginate()
        for e in p.get("Endpoints", [])
    ])

    # Studio / Canvas apps. THE expensive one: a Canvas session is ~$32-64/day
    # and keeps billing after the browser tab closes.
    def studio_apps():
        out = []
        for p in sm.get_paginator("list_apps").paginate():
            for a in p.get("Apps", []):
                if a.get("Status") in ("InService", "Pending"):
                    out.append(
                        f"{a.get('AppType')}/{a.get('AppName')} "
                        f"[{a.get('Status')}] in {a.get('DomainId')}"
                    )
        return out

    _check(findings, region, "studio/canvas apps", studio_apps)

    # MLflow tracking servers bill continuously while they exist. This is the
    # check the CLI-based sweep could not perform at all.
    _check(findings, region, "mlflow tracking servers", lambda: [
        t["TrackingServerName"]
        for t in sm.list_mlflow_tracking_servers().get("TrackingServerSummaries", [])
    ])

    # Notebook instances are pure EC2 billing while InService.
    _check(findings, region, "notebook instances", lambda: [
        n["NotebookInstanceName"]
        for p in sm.get_paginator("list_notebook_instances").paginate()
        for n in p.get("NotebookInstances", [])
        if n.get("NotebookInstanceStatus") in ("InService", "Pending")
    ])

    # EMR Serverless. An app in CREATED state with no pre-initialised capacity
    # does NOT bill at rest, but one with initialCapacity set does, so report
    # the capacity alongside the state instead of guessing.
    def emr_apps():
        out = []
        for p in emr.get_paginator("list_applications").paginate():
            for a in p.get("applications", []):
                if a.get("state") == "TERMINATED":
                    continue
                detail = emr.get_application(applicationId=a["id"])["application"]
                cap = detail.get("initialCapacity")
                note = "pre-initialised capacity SET (bills at rest)" if cap else "no pre-init capacity"
                out.append(f"{a['name']} [{a.get('state')}] - {note}")
        return out

    _check(findings, region, "emr-serverless apps", emr_apps)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Check nothing billable is left running. Makes no changes."
    )
    add_common_args(p, bucket=False, role=False)
    p.add_argument(
        "--regions",
        default=DEFAULT_REGIONS,
        help=f"Comma-separated regions to sweep (default {DEFAULT_REGIONS})",
    )
    args = p.parse_args()

    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    session = boto3.Session(profile_name=args.profile)

    print("=" * 68)
    print(f"Teardown verification - account {config.ACCOUNT}, profile {args.profile}")
    print(f"regions: {', '.join(regions)}")
    print("=" * 68)

    findings = Findings()
    for region in regions:
        sweep_region(findings, session, region)

    print()
    print("=" * 68)

    if findings.unknown:
        print("COULD NOT CHECK - verify these by hand:")
        for u in findings.unknown:
            print(f"  ? {u}")
        print()

    if findings.billable:
        print("STILL PRESENT - these can bill until removed:")
        for b in findings.billable:
            print(f"  ! {b}")
        print()
        print("Remove them, then re-run this script.")
        print("  Canvas/Studio apps : cleanup/kill_canvas.ps1 -All")
        print("  everything else    : cleanup/cleanup.ps1 -IncludeBucket")
        return 1

    if findings.unknown:
        print("Nothing billable found, BUT some checks could not run (see above).")
        print("Not reporting this as clean.")
        return 1

    print("CLEAN - nothing billable found, and every check ran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
