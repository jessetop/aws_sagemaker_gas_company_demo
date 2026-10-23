"""
Module 0 - Stage the open datasets to S3 (shared setup for the whole series).

SoCalGas edition. Natural-gas demand is overwhelmingly heating-driven, so the
series is built on the same question a gas utility actually asks: *given the
weather, how much gas does a county burn?* That needs four open datasets:

  1. NOAA GHCN-Daily observations  - the FACT table. Daily station readings,
     already in S3 as Hive-partitioned Parquet (YEAR=/ELEMENT=), so this is an
     S3-to-S3 server-side copy: no download, no CloudFront flakiness. We copy
     the WORLDWIDE partitions on purpose and let Spark filter to California --
     that filter is real work, and it is what makes Module 02 (EMR/Glue Spark)
     worth demoing.
  2. GHCN station metadata          - DIMENSION 1 (3,241 California stations).
     Fixed-width text; parsed here into CSV.
  3. CEC natural-gas consumption    - DIMENSION 2 + the LABEL source. County x
     month x sector therms, 2008-2024. Published as .xlsx, converted to CSV.
  4. Census county centroids        - DIMENSION 3. Lets us map a station lat/lon
     to a county via a nearest-centroid join (Module 02).

Every later demo reads from the locations this script writes.

Cost: S3 storage only. The default 2015-2024 window is a few hundred MB
(~$0.01/month). All sources are free and public; credentials are only needed to
WRITE to your bucket.

Usage:
    python stage_dataset.py                       # uses demo.env defaults
    python stage_dataset.py --start-year 2008     # full CEC-aligned range
    python stage_dataset.py --elements TMAX,TMIN  # skip precipitation
    python stage_dataset.py --skip-observations   # lookups only (fast re-run)

Requirement traceability (Kiro Req 1): public dataset >100k samples (California
alone is ~200k rows per element per year), uploaded to a learner-provided S3
path, with retries on download failure and clear errors on upload failure.
"""

import argparse
import io
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import ClientError

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args

# ---------------------------------------------------------------- sources
# NOAA GHCN-Daily on the AWS Open Data Registry. Public, no credentials.
GHCN_BUCKET = "noaa-ghcn-pds"
GHCN_PARQUET_PREFIX = "parquet/by_year"
GHCN_STATIONS_KEY = "ghcnd-stations.txt"

# California Energy Commission QFER consumption tables (CEC Form 1308B).
CEC_COUNTY_MONTHLY_URL = "https://www.energy.ca.gov/filebrowser/download/9966?fid=9966"
CEC_UTILITY_MONTHLY_URL = "https://www.energy.ca.gov/filebrowser/download/9965?fid=9965"

# US Census 2020 county gazetteer - county centroids (INTPTLAT / INTPTLONG).
CENSUS_GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2020_Gazetteer/2020_Gaz_counties_national.zip"
)

# Default weather elements. TMAX/TMIN give us heating-degree-days; PRCP is a
# useful extra feature and makes the partition-pruning lesson concrete.
DEFAULT_ELEMENTS = ["TMAX", "TMIN", "PRCP"]

# CEC consumption starts in 2008. We default to a shorter window so class setup
# is quick; pass --start-year 2008 to align the full range.
DEFAULT_START_YEAR = 2015
DEFAULT_END_YEAR = 2024

# ------------------------------------------------- destination key contract
# The rest of the series reads from exactly these prefixes.
OBS_PREFIX = "raw/observations"          # GHCN daily Parquet (partitioned)
STATIONS_KEY = "raw/stations/ghcnd_stations_ca.csv"
COUNTIES_KEY = "raw/counties/ca_county_centroids.csv"
CONSUMPTION_KEY = "raw/consumption/cec_ng_county_monthly.csv"
UTILITY_KEY = "raw/consumption/cec_ng_utility_monthly.csv"


def download_with_retries(url: str, dest: Path, attempts: int = 3, delay: int = 5) -> None:
    """Download `url` to `dest`, retrying up to `attempts` times (Kiro Req 1.5)."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            print(f"  downloading {url} (attempt {attempt}/{attempts})")
            urlretrieve(url, dest)
            return
        except (URLError, OSError) as exc:  # network / source unavailable
            last_error = exc
            print(f"  attempt {attempt} failed: {exc}")
            if attempt < attempts:
                time.sleep(delay)
    raise RuntimeError(
        f"Failed to download {url} after {attempts} attempts. Last error: {last_error}"
    )


def put_bytes(s3, bucket: str, key: str, body: bytes) -> None:
    """Upload an in-memory object, surfacing exactly which key failed (Kiro Req 1.6)."""
    try:
        print(f"  writing s3://{bucket}/{key}  ({len(body):,} bytes)")
        s3.put_object(Bucket=bucket, Key=key, Body=body)
    except ClientError as exc:
        raise RuntimeError(f"Upload failed for s3://{bucket}/{key}: {exc}") from exc


def copy_ghcn_observations(public_s3, s3, bucket, years, elements) -> int:
    """Server-side copy the GHCN Parquet partitions we need into the demo bucket.

    GHCN is partitioned YEAR=<yyyy>/ELEMENT=<code>, so we copy only the slices
    the series uses instead of the whole archive. We keep the partition
    directory names so Spark/Glue infer them as Hive partitions for free -- and
    so "prune the partitions you do not need" is demonstrable in class.
    """
    copied = 0
    for year in years:
        for element in elements:
            src_prefix = f"{GHCN_PARQUET_PREFIX}/YEAR={year}/ELEMENT={element}/"
            # List with an UNSIGNED client: the NOAA bucket is public, and a
            # signed request from an unrelated account can be refused.
            pages = public_s3.get_paginator("list_objects_v2").paginate(
                Bucket=GHCN_BUCKET, Prefix=src_prefix
            )
            keys = [o["Key"] for page in pages for o in page.get("Contents", [])]
            if not keys:
                print(f"  ! no objects for YEAR={year} ELEMENT={element} (skipping)")
                continue
            for key in keys:
                dest = f"{OBS_PREFIX}/YEAR={year}/ELEMENT={element}/{key.rsplit('/', 1)[-1]}"
                try:
                    s3.copy_object(
                        Bucket=bucket,
                        Key=dest,
                        CopySource={"Bucket": GHCN_BUCKET, "Key": key},
                    )
                except ClientError as exc:
                    raise RuntimeError(
                        f"Copy failed s3://{GHCN_BUCKET}/{key} -> s3://{bucket}/{dest}: {exc}"
                    ) from exc
                copied += 1
            print(f"  YEAR={year} ELEMENT={element}: copied {len(keys)} object(s)")
    return copied


def build_station_csv(public_s3, tmp_dir: Path) -> bytes:
    """Parse the fixed-width GHCN station list down to the California subset.

    GHCN ships station metadata as fixed-width text (documented in the bucket
    readme.txt), NOT delimited -- so the column offsets below are the spec, not
    a guess. Note there is no county field; that is exactly why we do a
    nearest-centroid join against the Census file in Module 02.
    """
    local = tmp_dir / "ghcnd-stations.txt"
    print(f"  downloading s3://{GHCN_BUCKET}/{GHCN_STATIONS_KEY}")
    public_s3.download_file(GHCN_BUCKET, GHCN_STATIONS_KEY, str(local))

    rows = ["station_id,latitude,longitude,elevation_m,state,station_name"]
    kept = 0
    with open(local, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            # Fixed-width per the GHCN readme: ID 1-11, LAT 13-20, LON 22-30,
            # ELEV 32-37, STATE 39-40, NAME 42-71 (1-indexed, inclusive).
            if line[0:2] != "US" or line[38:40] != "CA":
                continue
            station_id = line[0:11].strip()
            lat = line[12:20].strip()
            lon = line[21:30].strip()
            elev = line[31:37].strip()
            name = line[41:71].strip().replace(",", " ")
            rows.append(f"{station_id},{lat},{lon},{elev},CA,{name}")
            kept += 1
    print(f"  California stations: {kept:,}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def build_county_csv(tmp_dir: Path) -> bytes:
    """Extract California county centroids from the Census gazetteer zip."""
    zip_path = tmp_dir / "gaz_counties.zip"
    download_with_retries(CENSUS_GAZETTEER_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        member = next(n for n in zf.namelist() if n.endswith(".txt"))
        raw = zf.read(member).decode("latin-1")

    rows = ["county_fips,county_name,county_key,latitude,longitude,land_sq_mi"]
    kept = 0
    for i, line in enumerate(raw.splitlines()):
        parts = line.split("\t")
        if i == 0 or len(parts) < 10 or parts[0].strip() != "CA":
            continue
        fips = parts[1].strip()
        name = parts[3].strip()
        land = parts[6].strip()
        lat = parts[8].strip()
        lon = parts[9].strip()
        # `county_key` is the join key to the CEC table, which spells counties
        # in caps and without the "County" suffix ("LOS ANGELES"). We join on
        # this name, NOT on a number: CEC's COUNTY_NUM is an alphabetical index,
        # not the Census FIPS code -- a genuine trap worth showing in class.
        key = name.upper().replace(" COUNTY", "").strip()
        rows.append(f"{fips},{name},{key},{lat},{lon},{land}")
        kept += 1
    print(f"  California counties: {kept}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def build_cec_csv(url: str, tmp_dir: Path, label: str) -> bytes:
    """Download a CEC .xlsx consumption table and convert it to CSV.

    Kept deliberately raw -- no aggregation. The CEC county table carries up to
    5 rows per (year, month, county, sector) because it breaks consumption down
    further, and the agency names have trailing-whitespace duplicates. Cleaning
    both is part of the pipeline the learners build, so we must not pre-clean it
    here.
    """
    import pandas as pd

    xlsx = tmp_dir / f"{label}.xlsx"
    download_with_retries(url, xlsx)
    df = pd.read_excel(xlsx)
    print(f"  {label}: {len(df):,} rows x {len(df.columns)} cols  {list(df.columns)}")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage NOAA GHCN weather + CEC gas consumption data to S3."
    )
    add_common_args(parser, role=False)
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument(
        "--elements",
        default=",".join(DEFAULT_ELEMENTS),
        help="Comma-separated GHCN element codes (default TMAX,TMIN,PRCP)",
    )
    parser.add_argument(
        "--skip-observations",
        action="store_true",
        help="Only stage the small lookup/consumption files (fast re-run)",
    )
    args = parser.parse_args()

    if args.start_year > args.end_year:
        parser.error("--start-year must be <= --end-year")
    years = list(range(args.start_year, args.end_year + 1))
    elements = [e.strip().upper() for e in args.elements.split(",") if e.strip()]

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = session.client("s3")
    # Unsigned client for the public NOAA bucket.
    public_s3 = session.client("s3", config=Config(signature_version=UNSIGNED))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        print("Step 1/4: GHCN station metadata (dimension)")
        put_bytes(s3, args.bucket, STATIONS_KEY, build_station_csv(public_s3, tmp_dir))

        print("Step 2/4: Census county centroids (dimension)")
        put_bytes(s3, args.bucket, COUNTIES_KEY, build_county_csv(tmp_dir))

        print("Step 3/4: CEC natural-gas consumption (label source)")
        put_bytes(
            s3, args.bucket, CONSUMPTION_KEY,
            build_cec_csv(CEC_COUNTY_MONTHLY_URL, tmp_dir, "cec_ng_county_monthly"),
        )
        put_bytes(
            s3, args.bucket, UTILITY_KEY,
            build_cec_csv(CEC_UTILITY_MONTHLY_URL, tmp_dir, "cec_ng_utility_monthly"),
        )

        if args.skip_observations:
            print("Step 4/4: skipped (--skip-observations)")
        else:
            print(
                f"Step 4/4: GHCN observations (fact) - "
                f"{len(years)} year(s) x {len(elements)} element(s), S3-to-S3 copy"
            )
            n = copy_ghcn_observations(public_s3, s3, args.bucket, years, elements)
            print(f"  copied {n:,} Parquet object(s)")

    print(f"\nDone. Raw data staged under s3://{args.bucket}/raw/")
    print("  observations/  GHCN daily Parquet  (YEAR=/ELEMENT= partitions)")
    print("  stations/      California station metadata")
    print("  counties/      California county centroids")
    print("  consumption/   CEC county + utility monthly therms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
