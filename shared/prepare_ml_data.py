"""
Prepare the supervised ML dataset shared by Modules 3-7.

Reads the processed taxi Parquet (output of the Module 1/2 pipeline), turns it
into a tabular **classification** problem, splits it, and writes train/val/test
CSVs back to S3. Everything downstream (Feature Store, Training, Tuning,
Clarify/Debugger, Deployment) consumes these splits.

Task: among **card-paying** riders (the only ones whose tip is reliably recorded),
predict `high_tip` = tipped > 20% of fare. Filtering to card payments avoids the
obvious leak that cash trips always record tip = 0.

Runs locally with pandas/pyarrow (free) — the processed data is small once we
project columns and filter. Sampling keeps training fast and cheap while still
exceeding 100k samples (Kiro Req 1).

Usage:
    python prepare_ml_data.py --bucket roi-smdemo-029331796573-us-east-1 \
        --profile roitraining --region us-east-1 --sample 150000
"""

import argparse
import io
import sys

import boto3
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as fs

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args

# Feature columns fed to the model (plus the engineered categoricals we one-hot).
NUMERIC = [
    "trip_distance",
    "trip_duration_min",
    "trip_speed_mph",
    "pickup_hour",
    "passenger_count",
    "fare_amount",
]
CATEGORICAL = ["trip_distance_bucket", "pickup_borough"]
BOOL = ["is_airport_trip"]
TARGET = "high_tip"


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p, role=False)
    p.add_argument("--sample", type=int, default=150_000)
    p.add_argument("--source-prefix", default="processed/emr")
    p.add_argument("--out-prefix", default="ml/taxi")
    args = p.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    creds = session.get_credentials().get_frozen_credentials()
    s3fs = fs.S3FileSystem(
        access_key=creds.access_key,
        secret_key=creds.secret_key,
        session_token=creds.token,
        region=args.region,
    )

    # Read only the columns we need, filtered to card payments, straight from S3.
    print("reading processed data from S3...")
    dataset = ds.dataset(
        f"{args.bucket}/{args.source_prefix}",
        filesystem=s3fs,
        format="parquet",
        partitioning="hive",
    )
    cols = NUMERIC + CATEGORICAL + BOOL + ["payment_label", "tip_pct"]
    table = dataset.to_table(
        columns=cols, filter=pc.field("payment_label") == "Credit card"
    )
    df = table.to_pandas()
    print(f"card-payment rows: {len(df):,}")

    # Build the label, then drop the columns that would leak it.
    df[TARGET] = (df["tip_pct"] > 20).astype(int)
    df = df.drop(columns=["payment_label", "tip_pct"])

    # Sample for cheap/fast training (still > 100k).
    if len(df) > args.sample:
        df = df.sample(n=args.sample, random_state=42).reset_index(drop=True)
    print(f"sampled rows: {len(df):,}  | positive rate: {df[TARGET].mean():.3f}")

    # One-hot encode categoricals; cast bool to int. Keep label as the FIRST
    # column (the convention SageMaker built-in algorithms expect, and easy for
    # a custom script too).
    df[BOOL] = df[BOOL].astype(int)
    df = pd.get_dummies(df, columns=CATEGORICAL, drop_first=True)
    # pandas >=2 get_dummies returns bool columns. Cast to int so the CSVs are
    # purely numeric — required for clean CSV inference at the endpoint AND for
    # Feature Store, which cannot infer a feature type from a bool dtype.
    bool_cols = df.select_dtypes(include="bool").columns
    df[bool_cols] = df[bool_cols].astype(int)
    df = df.dropna()
    label = df.pop(TARGET)
    df.insert(0, TARGET, label)

    # 70/15/15 split (Kiro Req 1 defaults).
    n = len(df)
    train = df.iloc[: int(0.70 * n)]
    val = df.iloc[int(0.70 * n) : int(0.85 * n)]
    test = df.iloc[int(0.85 * n) :]
    print(f"train={len(train):,} val={len(val):,} test={len(test):,}")

    s3 = session.client("s3")
    for name, part in [("train", train), ("validation", val), ("test", test)]:
        buf = io.StringIO()
        part.to_csv(buf, index=False)
        key = f"{args.out_prefix}/{name}/{name}.csv"
        s3.put_object(Bucket=args.bucket, Key=key, Body=buf.getvalue())
        print(f"  wrote s3://{args.bucket}/{key}")

    # Also save the feature column order so inference can rebuild rows correctly.
    feat_cols = list(df.columns)
    s3.put_object(
        Bucket=args.bucket,
        Key=f"{args.out_prefix}/feature_columns.txt",
        Body="\n".join(feat_cols),
    )
    print(f"feature columns ({len(feat_cols)}): {feat_cols}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
