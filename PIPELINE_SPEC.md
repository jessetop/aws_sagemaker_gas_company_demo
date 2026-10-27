# The One Pipeline — canonical transformation spec

Every demo in this series implements **the same pipeline** on **the same data**.
Only the *tool* changes. When you teach, you point at one slice ("the join",
"the pivot") and show how each environment expresses it. This file is the
contract all the implementations agree on.

Single source of truth: [`shared/gas_transforms.py`](shared/gas_transforms.py).
It uses only the standard PySpark DataFrame API — no GlueContext, no SageMaker
SDK — so the same function runs unchanged on Glue, EMR Serverless, a Studio
notebook, or local Spark.

---

## Inputs

| Item | Source | Size | Role |
|---|---|---|---|
GHCN-Daily observations | NOAA, via `s3://noaa-ghcn-pds` | **201,486,363 rows** for 2015-2024 × TMAX/TMIN/PRCP | fact |
GHCN station metadata | NOAA, fixed-width text | 3,241 California stations | dimension |
County centroids | US Census 2020 Gazetteer | 58 California counties | dimension |
Gas consumption | California Energy Commission QFER | 19,064 county-month-sector rows, 2008-2024 | **label source** |

Staged to `s3://<bucket>/raw/` by `00-setup/stage_dataset.py`.

### Raw observation schema (verified)

```
ID          string   station identifier, e.g. "USW00023174"
DATE        string   "20240115"  <- a STRING, not a date
DATA_VALUE  long     integer in TENTHS of a degree C.  390 = 39.0 C
M_FLAG      string   measurement flag
Q_FLAG      string   quality flag — populated ONLY when a reading FAILED QC
S_FLAG      string   source flag
OBS_TIME    string   observation time
```

Partitioned `YEAR=<yyyy>/ELEMENT=<code>`, which Spark reads as columns — so
filtering on either prunes whole directories.

### Three traps, deliberately left in

These are not accidents of the source data we work around quietly. They are the
teaching material, so the learners fix them rather than inheriting a clean file.

1. **`DATE` is a string.** Cast it carelessly and Spark's CORRECTED parser
   returns NULL, silently deleting rows rather than erroring.
2. **`DATA_VALUE` is in tenths of a degree C.** Miss it and every number is
   plausible and ten times wrong.
3. **`Q_FLAG` is inverted from intuition.** It is set only when a reading
   *failed* quality control, so "good data" means the flag is empty.

Two more live in the CEC file:

4. **`COUNTY_NUM` is not a FIPS code.** It is an alphabetical index
   (Alameda=1, Alpine=2, Amador=3) while Census FIPS runs 001, 003, 005. Join on
   it and you mis-assign nearly every county — quietly. We join on the
   normalised county *name*.
5. **CEC ships up to 5 rows per county-month-sector** and pads name fields with
   trailing whitespace. Summing is mandatory; assuming one row per group
   undercounts demand roughly 3×.

---

## The transformations

| # | Step | Type | Why it's here |
|---|---|---|---|
T0 | Read 4 sources | Source | 4 source nodes on a visual canvas |
T1 | Rename to snake_case | Schema | raw GHCN columns are SHOUTED and cryptic |
T2 | Drop rows missing station/date/value | Cleaning | the fields everything depends on |
**T2b** | **Broadcast semi-join to California stations** | **Filter** | **before the shuffle — see below** |
T3 | Parse `DATE` string → date | Parse | explicit format; a silent cast deletes rows |
T4 | Quality filter on `Q_FLAG` | Filter | keep only readings the source trusts |
T5 | Rescale tenths → real units | Derive | `/10.0` |
T6 | Range filter, plausible temps | Filter | before they poison the pivot |
T7 | **Pivot** long → wide per station-day | **Reshape** | the headline wide shuffle |
T8 | Require both TMAX and TMIN | Filter | HDD needs both bounds |
T9 | Derive `temp_mean_f`, `temp_range_c` | Derive | combines two columns + a unit change |
T10 | Derive **`hdd65`** | Derive | `max(0, 65 − mean°F)` — the domain metric |
T11 | Calendar features | Derive | year, month, day-of-week, weekend flag |
T12 | Map month → season label | Encode | classic "map values" transform |
T13 | Bin `hdd65` → band | Bin | none / mild / moderate / cold / severe |
T14 | Flag `is_heating_season` | Derive | November–March |
T15 | **Join** station dimension (itself nearest-county joined) | **Join** | a join of a join |
T16 | **Join** CEC consumption on county + year + month | **Join** | attaches therms; changes grain |
T17 | Final projection | Schema | 25 analytics-ready columns |
T18\* | *(ML modules only)* add `high_demand` label | Label | top-quartile therms **within county** |

\* `add_ml_label()` — see the leakage notes below.

### T2b: why the filter comes before the pivot

GHCN is global. Ten years of three elements is ~200 million rows and California
is about 5% of that. Running T7's pivot first and joining the station dimension
afterwards shuffles 200M rows to discard 190M of them.

A semi-join against the 3,241-row station list is a broadcast join — no shuffle
— and cuts the input ~20× before the first expensive step.

**Measured, so the claim is honest:** 643 s/$0.3144 → 597 s/$0.2919. About
**7%**, with byte-identical output. Not the landslide it looks like it should
be, because the pivot was never the bottleneck — both versions still scan all
200M rows off S3, and that I/O dominates.

Which makes this the best *measurement* lesson in the series rather than the
best optimisation one. Partition pruning buys far more here than anything you
do to the shuffle.

### T15: the station→county join has no key

GHCN station metadata has latitude, longitude and elevation — but **no county**.
So the mapping is derived: cross-join 3,241 stations against 58 county
centroids and keep the nearest.

Two things worth saying out loud. A cross join is usually a mistake, but against
a 58-row dimension it is correct and cheap — and computed **once on the
dimension**, never on the fact table. And it uses squared euclidean distance on
lat/lon rather than great-circle: over one state that ranks neighbours
identically, but it would be wrong at continental scale. Approximations need
their domain stated.

---

## Output

```
s3://<bucket>/processed/visual-etl/
  obs_year=2015..2024 / obs_month=1..12 /*.parquet
```

**1,668,673 rows, 25 columns.** Partitioned by year+month rather than by day: a
California station-month is a sensible Parquet file size, whereas partitioning
by date would emit thousands of tiny files.

Because every tool runs the same logic, the outputs are identical — a good thing
to show learners. The result doesn't depend on the tool, only the experience of
building it does.

---

## The label, and two ways to fool yourself

`add_ml_label()` adds `high_demand`: 1 when a county-month's total therms sits
in the **top quartile for that county**.

**Ranked within county, not globally.** Los Angeles burns orders of magnitude
more gas than Alpine. A global threshold would just rediscover which counties
are big — the model would score well by memorising county and learn nothing
about weather.

**The therms columns are dropped** immediately after the label is computed from
them. Leaving any in lets the model read the answer off its own input.

### Group structure

CEC consumption is **monthly**, so every daily row inside a county-month carries
the same label. A random row-level split puts the same county-month on both
sides, the model sees its test labels during training, and the score is inflated
for free. `shared/prepare_ml_data.py` splits by **county-month group**;
`--random-split` reproduces the inflated number for contrast.

### Known limitation — read before quoting any metric

The label is a county-**month** aggregate while the features are a single
station-**day**. One day's weather cannot indicate whether a whole month was
anomalous. Measured consequence:

| | AUC |
|---|---|
all features | 0.9235 |
calendar only | 0.9043 |
weather only | 0.8298 |
**deseasonalised label** | **0.5159** |

`season_Winter` alone carries 0.705 of the feature importance. The 0.92 is a
calendar lookup, not a weather model.

**The fix** (not yet implemented): aggregate features to station-month to match
the label's grain — mean/min/max temperature, total HDD, days below freezing,
total precipitation. That is also the real utility-forecasting formulation, and
~3,241 stations × 120 months still leaves several hundred thousand rows.
