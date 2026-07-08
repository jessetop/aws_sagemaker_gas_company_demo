"""
Managed MLflow tracking server — the NEW-way replacement for SageMaker Experiments.

NOT run by default: a tracking server bills CONTINUOUSLY (~$0.64/hr ≈ $15/day) from
creation until you delete it, and takes ~25-40 min to provision. So this is a
ready-to-go helper you invoke when you actually want it (e.g. ~40 min before class),
then tear down right after.

    python mlflow_tracking_server.py --create ...   # provision (then wait ~30 min)
    python mlflow_tracking_server.py --status ...    # check provisioning state
    python mlflow_tracking_server.py --delete ...    # STOP THE BILLING

Old way: SageMaker Experiments (Studio Classic "Experiments" panel) — already
populated by this series. New way: log the same runs to this MLflow server and
browse them in the MLflow UI (same UI as open-source MLflow), launched from Studio.
"""

import argparse
import sys

import boto3

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args

SERVER = "roi-smdemo-mlflow"
DZ_TAGS = [
    {"Key": "AmazonDataZoneProject", "Value": "azjpw3giqinpux"},
    {"Key": "AmazonDataZoneDomain", "Value": "dzd-6jlg4btaz2tp49"},
    {"Key": "AmazonDataZoneEnvironment", "Value": "cuv9xh4sdcppyh"},
]


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--delete", action="store_true")
    args = p.parse_args()

    sm = boto3.Session(profile_name=args.profile, region_name=args.region).client("sagemaker")

    if args.create:
        sm.create_mlflow_tracking_server(
            TrackingServerName=SERVER,
            ArtifactStoreUri=f"s3://{args.bucket}/mlflow/",
            TrackingServerSize="Small",        # cheapest
            RoleArn=args.role_arn,
            AutomaticModelRegistration=False,
            Tags=DZ_TAGS,
        )
        print(f"creating '{SERVER}' (~25-40 min). $$ BILLING STARTS NOW (~$15/day) "
              f"until --delete. Poll with --status.")
    elif args.status:
        d = sm.describe_mlflow_tracking_server(TrackingServerName=SERVER)
        print("status:", d["TrackingServerStatus"], "| URL:", d.get("TrackingServerUrl", "(pending)"))
    elif args.delete:
        sm.delete_mlflow_tracking_server(TrackingServerName=SERVER)
        print(f"deleting '{SERVER}' — billing stops once deletion completes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
