"""
Module 3 — SageMaker Feature Store (Kiro-adjacent), the old way.

Creates a FeatureGroup for the engineered gas-demand features and ingests a small
batch. This is the classic SageMaker AI experience: define a schema in code,
create online + offline stores, and call ingest() from the SDK.

The NEW way surfaces the same feature group as a governed asset in the Unified
Studio catalog (discoverable, permissioned, lineage-tracked) — see WALKTHROUGH.md.

Cost note: we ingest only a small sample and disable the online store by default
(offline store is just S3) to keep cost negligible. Pass --online to demo the
online store, then delete the group promptly.

Usage:
    python feature_store_ingest.py --bucket roi-smdemo-029331796573-us-east-1 \
        --role-arn arn:aws:iam::029331796573:role/roi-smdemo-exec-role \
        --profile roitraining --region us-east-1 --rows 2000
"""

import argparse
import io
import re
import sys
import time

import boto3
import pandas as pd
import sagemaker
from sagemaker.feature_store.feature_group import FeatureGroup

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)  # --profile / --region / --bucket / --role-arn
    p.add_argument("--rows", type=int, default=2000)
    p.add_argument("--online", action="store_true", help="enable online store")
    p.add_argument("--prefix", default="ml/gas")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)

    # Load a small sample of the prepared features to define + populate the group.
    # (Read via boto3 to avoid an s3fs dependency.)
    s3 = boto_sess.client("s3")
    csv_bytes = s3.get_object(
        Bucket=args.bucket, Key=f"{args.prefix}/train/train.csv"
    )["Body"].read()
    df = pd.read_csv(io.BytesIO(csv_bytes)).head(args.rows)

    # Feature Store feature names must match [a-zA-Z0-9]([-_]*[a-zA-Z0-9]){0,63}
    # — no spaces or slashes. Our one-hot columns (e.g. "pickup_borough_Staten
    # Island", "pickup_borough_N/A") have both, so sanitize them here. The
    # training CSVs keep the readable names; only the feature group is sanitized.
    df.columns = [re.sub(r"[^a-zA-Z0-9]+", "_", c).strip("_") for c in df.columns]

    # Feature Store needs a record-identifier and an event-time column.
    df = df.reset_index().rename(columns={"index": "trip_id"})
    df["event_time"] = float(time.time())
    df["trip_id"] = df["trip_id"].astype("string")

    fg_name = config.resource("features")
    fg = FeatureGroup(name=fg_name, sagemaker_session=sm_sess)
    fg.load_feature_definitions(data_frame=df)  # infers schema from the DataFrame

    fg.create(
        s3_uri=f"s3://{args.bucket}/feature-store/",
        record_identifier_name="trip_id",
        event_time_feature_name="event_time",
        role_arn=args.role_arn,
        enable_online_store=args.online,
        tags=[{"Key": "Project", "Value": "sagemaker-unified-studio-demos"}],
    )

    # Wait until the group is Created before ingesting.
    while fg.describe().get("FeatureGroupStatus") == "Creating":
        time.sleep(5)
    print("feature group:", fg.describe().get("FeatureGroupStatus"))

    fg.ingest(data_frame=df, max_workers=2, wait=True)
    print(f"ingested {len(df)} records into {fg_name}")
    print("offline store (S3):", f"s3://{args.bucket}/feature-store/")
    print("To remove: fg.delete()  (or the cleanup script)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
