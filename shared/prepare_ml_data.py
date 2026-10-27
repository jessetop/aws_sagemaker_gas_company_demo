"""
Prepare the supervised ML dataset shared by Modules 3-7.

Reads the processed gas/weather Parquet (output of the Module 1/2 pipeline),
turns it into a tabular **classification** problem, splits it, and writes
train/val/test CSVs back to S3. Everything downstream (Feature Store, Training,
Tuning, Clarify/Debugger, Deployment) consumes these splits.

Task: from the weather at a station on a day, predict whether that station's
county was in a **high gas demand** month -- `high_demand` = county-month total
therms in the top quartile *for that county*.

Two things about this framing are deliberate, and both are worth saying out loud
in class because getting either wrong produces a model that scores well and
means nothing.

1. THE LABEL IS RANKED WITHIN COUNTY, NOT GLOBALLY. Los Angeles burns orders of
   magnitude more gas than Alpine. A global threshold would just rediscover
   which counties are big: the model would hit a high AUC by memorising
   `county`, and would have learned nothing about weather. Ranking inside each
   county forces the weather signal to do the work.

2. THE THERMS COLUMNS ARE DROPPED. `total_therms`, `res_therms` and
   `nonres_therms` are what the label is computed FROM. Leaving any of them in
   the feature set lets the model read the answer off its own input -- the gas
   same shape as any "the label is computed from this column" leak, and much
   easier to do by accident because the column names look innocent.

GROUP STRUCTURE / SPLITTING (the real lesson here)
--------------------------------------------------
CEC consumption is MONTHLY, so every daily row inside one county-month carries
the same label. A random row-level split therefore puts rows from the same
county-month on both sides of the split, the model effectively sees test labels
during training, and the score is inflated for free.

So we split by **county-month group**, not by row. The difference is usually
several AUC points of pure self-deception, and it is easy to demonstrate live:
pass --random-split to reproduce the inflated number, then compare.

Runs locally with pandas/pyarrow (free) -- the processed data is small once we
project columns. Sampling keeps training fast and cheap while still exceeding
100k samples (Kiro Req 1).

Usage:
    python shared/prepare_ml_data.py
    python shared/prepare_ml_data.py --sample 150000
    python shared/prepare_ml_data.py --random-split   # the WRONG way, for contrast
"""

import argparse
import io
import sys

import boto3
import numpy as np
import pandas as pd
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
    "temp_max_c",
    "temp_min_c",
    "temp_mean_f",
    "temp_range_c",
    "precip_mm",
    "hdd65",
    "elevation_m",
    "obs_month",
]
CATEGORICAL = ["hdd_bucket", "season"]
BOOL = ["is_weekend", "is_heating_season"]
# Added at runtime by the precipitation imputation below, not read from source.
DERIVED_INT = ["precip_reported"]
TARGET = "high_demand"

# Read but never used as features: the label is derived from these, so they are
# dropped immediately afterwards. See the module docstring.
LABEL_SOURCE = ["total_therms"]
# Carried through to build the group key for splitting, then dropped.
GROUP_KEYS = ["county_key", "obs_year"]

# County is deliberately NOT a feature. Because the label is ranked within
# county, county carries no signal by construction -- including it would add 49
# one-hot columns of pure noise and invite the "but my feature importance says
# county matters" confusion.


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p, role=False)
    p.add_argument("--sample", type=int, default=150_000)
    p.add_argument("--source-prefix", default="processed/visual-etl")
    p.add_argument("--out-prefix", default="ml/gas")
    p.add_argument(
        "--random-split",
        action="store_true",
        help="Split rows at random instead of by county-month. WRONG on purpose: "
             "demonstrates the inflated score that group leakage buys you.",
    )
    p.add_argument("--quantile", type=float, default=0.75,
                   help="Within-county therms quantile above which a month is 'high demand'")
    p.add_argument(
        "--no-calendar",
        action="store_true",
        help="Drop obs_month / season / is_heating_season. Forces the model to use "
             "WEATHER instead of the calendar. Measured: AUC 0.92 -> 0.83, and the "
             "0.83 is the honest number (see --deseasonalize for why).",
    )
    p.add_argument(
        "--deseasonalize",
        action="store_true",
        help="Rank therms within county AND month-of-year, so the label asks 'was this "
             "January unusual for this county's Januaries?'. Removes the trivial "
             "seasonal signal and makes it a real weather-anomaly problem.",
    )
    args = p.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    creds = session.get_credentials().get_frozen_credentials()
    s3fs = fs.S3FileSystem(
        access_key=creds.access_key,
        secret_key=creds.secret_key,
        session_token=creds.token,
        region=args.region,
    )

    # Read only the columns we need, straight from S3. obs_year/obs_month are
    # Hive partition columns on the Module 1 output.
    print("reading processed data from S3...")
    dataset = ds.dataset(
        f"{args.bucket}/{args.source_prefix}",
        filesystem=s3fs,
        format="parquet",
        partitioning="hive",
    )
    cols = sorted(set(NUMERIC + CATEGORICAL + BOOL + LABEL_SOURCE + GROUP_KEYS))
    df = dataset.to_table(columns=cols).to_pandas()
    print(f"rows: {len(df):,}")
    if df.empty:
        print(f"ERROR: no rows under s3://{args.bucket}/{args.source_prefix}/")
        print("Run Module 1 first (01-data-prep/new-visual-etl/run_glue_job.py --start).")
        return 1

    # ---- label: top-quartile therms WITHIN each county ---------------------
    # Rank inside the county so the model cannot win by memorising county size.
    #
    # DEFAULT (--deseasonalize off) ranks within county only. Be aware what that
    # produces: gas demand is overwhelmingly seasonal, so a county's top-quartile
    # months ARE its winter months, and the calendar nearly determines the label.
    # Measured on this data, the resulting model is 92% a calendar lookup:
    #
    #     all features      AUC 0.9235   season_Winter importance 0.705
    #                                    obs_month     importance 0.216
    #     calendar only     AUC 0.9043
    #     weather only      AUC 0.8298
    #
    # That 0.92 is not leakage -- the month is legitimately known at prediction
    # time -- but it is a degenerate task. The model learned "winter is cold and
    # people heat their homes", which is true and teaches nothing.
    #
    # --deseasonalize ranks within county AND month-of-year instead, so the
    # question becomes "was THIS January unusual for this county's Januaries?".
    # That strips out the seasonal gimme and leaves a genuine weather-anomaly
    # problem. Expect a much lower, much more interesting score.
    if args.deseasonalize:
        rank = df.groupby(["county_key", "obs_month"])["total_therms"].rank(pct=True)
        print("label: deseasonalised (ranked within county AND month-of-year)")
    else:
        rank = df.groupby("county_key")["total_therms"].rank(pct=True)
        print("label: ranked within county (seasonal; the calendar will dominate "
              "-- see --deseasonalize)")
    df[TARGET] = (rank > args.quantile).astype(int)
    print(f"positive rate: {df[TARGET].mean():.4f}  (target ~{1 - args.quantile:.2f})")

    # The group a row belongs to, for an honest split. One county-month is one
    # group because the label is constant across it.
    group = (
        df["county_key"].astype(str)
        + "|" + df["obs_year"].astype(str)
        + "|" + df["obs_month"].astype(str)
    )

    # Drop the label source NOW, before it can leak into the feature matrix.
    df = df.drop(columns=LABEL_SOURCE + ["county_key", "obs_year"])

    # ---- missing precipitation ---------------------------------------------
    # GHCN precipitation is missing for ~47% of California station-days: plenty
    # of stations report temperature but not rainfall. A null here means "not
    # measured", NOT "no rain", so we must not silently treat it as zero and we
    # must not throw the row away either -- dropping half the dataset to keep
    # one optional feature is a terrible trade.
    #
    # Standard fix: impute, and add an indicator so the model can tell "dry day"
    # apart from "no gauge". The indicator is the part people forget, and
    # without it the imputed zeros are indistinguishable from real zeros.
    n_missing = int(df["precip_mm"].isna().sum())
    if n_missing:
        print(f"precip_mm missing on {n_missing:,} rows ({n_missing / len(df) * 100:.1f}%)"
              f" -> imputing 0 + adding precip_reported flag")
    df["precip_reported"] = df["precip_mm"].notna().astype(int)
    df["precip_mm"] = df["precip_mm"].fillna(0.0)

    # Drop whatever nulls remain BEFORE sampling. Sampling first and dropping
    # afterwards means --sample is a lie: asking for 150,000 rows quietly
    # returned 79,485 because the drop happened second. Same class of mistake as
    # filtering after a shuffle instead of before it -- order decides the result.
    before = len(df)
    df = df.dropna()
    group = group.loc[df.index]
    if len(df) < before:
        print(f"dropped {before - len(df):,} rows still carrying nulls")

    # Sample for cheap/fast training (still > 100k).
    if len(df) > args.sample:
        idx = df.sample(n=args.sample, random_state=42).index
        df = df.loc[idx]
        group = group.loc[idx]
    print(f"rows for modelling: {len(df):,}")

    # One-hot encode categoricals; cast bool to int. Keep label as the FIRST
    # column (the convention SageMaker built-in algorithms expect, and easy for
    # a custom script too).
    df[BOOL] = df[BOOL].astype(int)
    df = pd.get_dummies(df, columns=CATEGORICAL, drop_first=True)
    # pandas >=2 get_dummies returns bool columns. Cast to int so the CSVs are
    # purely numeric -- required for clean CSV inference at the endpoint AND for
    # Feature Store, which cannot infer a feature type from a bool dtype.
    bool_cols = df.select_dtypes(include="bool").columns
    df[bool_cols] = df[bool_cols].astype(int)

    if args.no_calendar:
        cal = [c for c in df.columns
               if c == "obs_month" or c == "is_heating_season" or c.startswith("season_")]
        df = df.drop(columns=cal)
        print(f"--no-calendar: dropped {cal}")

    label = df.pop(TARGET)
    df.insert(0, TARGET, label)

    # ---- split -------------------------------------------------------------
    if args.random_split:
        # The WRONG way, kept deliberately so the inflated score can be shown
        # next to the honest one.
        print("!! --random-split: rows from one county-month will land on BOTH")
        print("!! sides of the split. Expect an optimistically inflated AUC.")
        shuffled = df.sample(frac=1.0, random_state=42)
        n = len(shuffled)
        train = shuffled.iloc[: int(0.70 * n)]
        val = shuffled.iloc[int(0.70 * n) : int(0.85 * n)]
        test = shuffled.iloc[int(0.85 * n) :]
    else:
        # Group split: every row of a county-month goes to exactly one side.
        groups = pd.Series(group.unique())
        groups = groups.sample(frac=1.0, random_state=42).reset_index(drop=True)
        n_g = len(groups)
        train_g = set(groups.iloc[: int(0.70 * n_g)])
        val_g = set(groups.iloc[int(0.70 * n_g) : int(0.85 * n_g)])
        print(f"county-month groups: {n_g:,} "
              f"(train {len(train_g):,} / val {len(val_g):,} / test {n_g - len(train_g) - len(val_g):,})")
        in_train = group.isin(train_g)
        in_val = group.isin(val_g)
        train = df[in_train]
        val = df[in_val]
        test = df[~in_train & ~in_val]

    print(f"train={len(train):,} val={len(val):,} test={len(test):,}")
    for name, part in (("train", train), ("validation", val), ("test", test)):
        if part.empty:
            print(f"ERROR: the {name} split is empty; lower --sample or widen the data range.")
            return 1
        print(f"  {name} positive rate: {part[TARGET].mean():.4f}")

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
