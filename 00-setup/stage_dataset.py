"""
Module 0 — Stage the open dataset to S3 (shared setup for the whole series).

Downloads one month of NYC Yellow Taxi trips (Parquet) and the taxi zone lookup
(CSV) from the official NYC TLC open-data distribution, then uploads them to the
demo S3 bucket. Every later demo reads from the locations this script writes.

Cost: a few cents of S3 storage (~48 MB). The dataset is free, public, no auth.

Usage:
    python stage_dataset.py \
        --bucket roi-smdemo-029331796573-us-east-1 \
        --profile roitraining --region us-east-1

Requirement traceability (Kiro Req 1): public dataset >100k samples (this has
~2.96M rows), uploaded to a learner-provided S3 path, with retries on download
failure and clear errors on upload failure.
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from urllib.request import urlretrieve
from urllib.error import URLError

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args

# Official NYC TLC open-data files (CloudFront-distributed, no credentials).
TRIPS_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet"
ZONES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"

# Where each file lands in the bucket (the contract the rest of the series reads).
TRIPS_KEY = "raw/trips/yellow_tripdata_2024-01.parquet"
ZONES_KEY = "raw/zones/taxi_zone_lookup.csv"


def download_with_retries(url: str, dest: Path, attempts: int = 3, delay: int = 5) -> None:
    """Download `url` to `dest`, retrying up to `attempts` times (Kiro Req 1.5)."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            print(f"  downloading {url} (attempt {attempt}/{attempts})")
            urlretrieve(url, dest)
            return
        except URLError as exc:  # network / source unavailable
            last_error = exc
            print(f"  attempt {attempt} failed: {exc}")
            if attempt < attempts:
                time.sleep(delay)
    raise RuntimeError(
        f"Failed to download {url} after {attempts} attempts. Last error: {last_error}"
    )


def upload(s3, bucket: str, src: Path, key: str) -> None:
    """Upload one file, surfacing exactly which object failed (Kiro Req 1.6)."""
    try:
        print(f"  uploading {src.name} -> s3://{bucket}/{key}")
        s3.upload_file(str(src), bucket, key)
    except ClientError as exc:
        raise RuntimeError(f"Upload failed for s3://{bucket}/{key}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage NYC taxi data to S3.")
    add_common_args(parser, role=False)
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = session.client("s3")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        trips_file = tmp_dir / "yellow_tripdata_2024-01.parquet"
        zones_file = tmp_dir / "taxi_zone_lookup.csv"

        print("Step 1/2: download open dataset from NYC TLC")
        download_with_retries(TRIPS_URL, trips_file)
        download_with_retries(ZONES_URL, zones_file)

        print("Step 2/2: upload splits to S3")
        upload(s3, args.bucket, trips_file, TRIPS_KEY)
        upload(s3, args.bucket, zones_file, ZONES_KEY)

    print(f"\nDone. Raw data staged under s3://{args.bucket}/raw/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
