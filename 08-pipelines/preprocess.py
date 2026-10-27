"""
Pipeline step 1 - ML prep (runs as a SageMaker Processing job).

Reads the PROCESSED gas/weather Parquet from the input channel, builds the
`high_demand` label, splits by county-month group, and writes headerless
train/validation/test CSVs (label first column) to the output channels.

WHY IT READS `processed/`, NOT `raw/`
------------------------------------
An earlier version of this file re-derived the whole transformation pipeline in
pandas, duplicating logic that already lived in the Spark module. That is how
the series ended up with two sources of truth that could silently drift -- the
README claimed one canonical pipeline while this file quietly reimplemented it.

So this step starts from the Glue/Spark output instead. Spark does the heavy
reshaping once (200M rows -> 1.67M California station-days); this step only does
the cheap, tabular ML prep that genuinely belongs in pandas.

A FIXED schema (no one-hot encoding) keeps the columns deterministic so the
downstream Clarify steps can declare headers reliably. That is the only reason
this differs from shared/prepare_ml_data.py, which does one-hot for the
standalone training path.

SageMaker Processing contract:
  input  : /opt/ml/processing/input                      (processed parquet)
  outputs: /opt/ml/processing/output/{train,validation,test}
"""

import os

import pandas as pd

IN_DIR = "/opt/ml/processing/input"
OUT = "/opt/ml/processing/output"

# Fixed, deterministic schema (label first) - shared with build_pipeline.py headers.
LABEL = "high_demand"
FEATURES = [
    "temp_max_c",
    "temp_min_c",
    "temp_mean_f",
    "temp_range_c",
    "precip_mm",
    "precip_reported",
    "hdd65",
    "elevation_m",
    "obs_month",
    "is_weekend",
    "is_heating_season",
]

# Read but never used as a feature: the label is computed from it and then it is
# dropped. Leaving it in would let the model read the answer off its own input.
LABEL_SOURCE = "total_therms"
# Needed to build the group key for an honest split, then dropped.
GROUP_COLS = ["county_key", "obs_year"]

QUANTILE = 0.75   # within-county therms quantile above which a month is "high"
SAMPLE = 150_000


def main() -> None:
    # Parquet files are mounted into the input dir, possibly nested by the
    # obs_year=/obs_month= partitions, so walk rather than listdir.
    files = []
    for root, _dirs, names in os.walk(IN_DIR):
        files += [os.path.join(root, n) for n in names if n.endswith(".parquet")]
    if not files:
        raise FileNotFoundError(f"no .parquet files under {IN_DIR}")
    print(f"input files: {len(files)}")

    cols = FEATURES + [LABEL_SOURCE] + GROUP_COLS
    df = pd.concat(
        [pd.read_parquet(f, columns=cols) for f in files], ignore_index=True
    )
    print(f"rows: {len(df):,}")

    # ---- label: top-quartile therms WITHIN each county --------------------
    # Ranked inside the county so the model cannot win by memorising which
    # counties are big. Los Angeles burns orders of magnitude more gas than
    # Alpine; a global threshold would just rediscover that.
    rank = df.groupby("county_key")[LABEL_SOURCE].rank(pct=True)
    df[LABEL] = (rank > QUANTILE).astype(int)
    print(f"positive rate: {df[LABEL].mean():.4f}")

    # One county-month is one group: the label is constant across it because
    # CEC consumption is monthly.
    group = (
        df["county_key"].astype(str)
        + "|" + df["obs_year"].astype(str)
        + "|" + df["obs_month"].astype(str)
    )

    # Precipitation is missing on ~47% of California station-days -- plenty of
    # stations measure temperature but not rain. A null means "no gauge", not
    # "no rain", so impute and flag rather than discarding half the dataset.
    df["precip_reported"] = df["precip_mm"].notna().astype(int)
    df["precip_mm"] = df["precip_mm"].fillna(0.0)

    df[["is_weekend", "is_heating_season"]] = df[
        ["is_weekend", "is_heating_season"]
    ].astype(int)

    # Drop nulls BEFORE sampling, or --sample is a lie.
    keep = df[[LABEL] + FEATURES].dropna().index
    df, group = df.loc[keep], group.loc[keep]

    if len(df) > SAMPLE:
        idx = df.sample(n=SAMPLE, random_state=42).index
        df, group = df.loc[idx], group.loc[idx]
    print(f"rows for modelling: {len(df):,}")

    out = df[[LABEL] + FEATURES]

    # ---- split by county-month GROUP, never by row ------------------------
    # A random row split puts the same county-month on both sides, so the model
    # sees its test labels during training and the score is inflated for free.
    groups = pd.Series(group.unique()).sample(frac=1.0, random_state=42)
    n_g = len(groups)
    train_g = set(groups.iloc[: int(0.70 * n_g)])
    val_g = set(groups.iloc[int(0.70 * n_g) : int(0.85 * n_g)])
    in_train, in_val = group.isin(train_g), group.isin(val_g)

    splits = {
        "train": out[in_train],
        "validation": out[in_val],
        "test": out[~in_train & ~in_val],
    }
    print(f"county-month groups: {n_g:,}")

    for name, part in splits.items():
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        # Headerless, label first -- what the training container expects.
        part.to_csv(os.path.join(d, f"{name}.csv"), index=False, header=False)
        print(f"  {name}: {len(part):,} rows -> {d}")

    print("done")


if __name__ == "__main__":
    main()
