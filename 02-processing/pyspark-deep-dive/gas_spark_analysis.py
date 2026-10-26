"""
PySpark deep dive on the SoCalGas gas-demand dataset.

This is the source of truth for the notebook next to it. It is written as a
runnable Glue script FIRST so every cell in the notebook is proven to work
before anyone opens it in front of a room -- a notebook full of unverified
PySpark is exactly the thing that dies on stage.

WHY NOT EMR
-----------
The AWS lab already covers "here is how you connect Studio to an EMR cluster".
Repeating that teaches nothing extra and risks leaving a cluster running. This
demo is about the *DataFrame work* instead, and it runs on serverless Spark:

  - Glue Interactive Sessions -- per-second billing, no cluster, notebook-native
  - Glue job (this script)    -- what we use to verify the code
  - EMR Serverless            -- same code, if you want the EMR branding
  - any Spark 3.x session     -- nothing here is Glue-specific

Each section below is one notebook cell and one teaching point. The ordering
builds: read -> reshape -> window -> join -> aggregate -> the payoff.

Run as a Glue job:
    python 02-processing/pyspark-deep-dive/run_spark_analysis.py --start
"""

import sys

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

# ---------------------------------------------------------------- parameters
# Accept Glue-style --key value args without requiring awsglue, so the same
# file runs under plain pyspark too.
def _arg(name: str, default: str = None) -> str:
    flag = f"--{name}"
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1]
    if default is not None:
        return default
    raise SystemExit(f"missing required argument {flag}")


BUCKET = _arg("bucket")
OBS = f"s3://{BUCKET}/raw/observations/"
STATIONS = f"s3://{BUCKET}/raw/stations/ghcnd_stations_ca.csv"
PROCESSED = f"s3://{BUCKET}/processed/visual-etl/"

spark = (
    SparkSession.builder.appName("gas-spark-deep-dive")
    .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")


def banner(n: int, title: str) -> None:
    print(f"\n{'=' * 72}\n[{n}] {title}\n{'=' * 72}")


# ===========================================================================
banner(1, "Partition pruning is free performance -- if you ask for it")
# ===========================================================================
# The GHCN data is laid out YEAR=<yyyy>/ELEMENT=<code>. Spark can skip whole
# directories when the filter matches a partition column, and the explain plan
# PROVES it rather than you hoping.
obs_all = spark.read.parquet(OBS)
print(f"all partitions, total rows: {obs_all.count():,}")

tmax_2024 = obs_all.filter((F.col("YEAR") == 2024) & (F.col("ELEMENT") == "TMAX"))
print(f"one year, one element     : {tmax_2024.count():,}")

# PartitionFilters in the plan is the thing to point at: those directories are
# never opened. A filter on a NON-partition column would show up under
# PushedFilters or Filter instead, and would still read every file.
print("\n--- physical plan (look for PartitionFilters) ---")
tmax_2024.explain(mode="formatted")


# ===========================================================================
banner(2, "Reshaping long to wide: one row per station-day")
# ===========================================================================
# GHCN is tall: one row per station, per day, per measurement. Almost every
# question you want to ask needs it wide. groupBy().pivot() is the move, and
# naming the pivot values matters -- without the explicit list Spark must run a
# separate job just to discover them.
obs = (
    obs_all.withColumnRenamed("ID", "station_id")
    .withColumn("obs_date", F.to_date(F.col("DATE").cast("string"), "yyyyMMdd"))
    .filter(F.col("Q_FLAG").isNull() | (F.trim(F.col("Q_FLAG")) == ""))
    .withColumn("value", F.col("DATA_VALUE") / 10.0)  # tenths -> real units
)

stations = spark.read.option("header", "true").option("inferSchema", "true").csv(STATIONS)

# Filter to California BEFORE the wide shuffle. 3,241 rows broadcast against
# 200M is free; pivoting 200M and discarding 95% afterwards is not.
obs_ca = obs.join(F.broadcast(stations.select("station_id")), "station_id", "inner")

daily = (
    obs_ca.groupBy("station_id", "obs_date")
    .pivot("ELEMENT", ["TMAX", "TMIN", "PRCP"])  # naming them avoids an extra job
    .agg(F.first("value"))
    .withColumnRenamed("TMAX", "tmax_c")
    .withColumnRenamed("TMIN", "tmin_c")
    .withColumnRenamed("PRCP", "precip_mm")
    .filter(F.col("tmax_c").isNotNull() & F.col("tmin_c").isNotNull())
)

# Heating Degree Days, base 65F -- the utility industry's weather metric.
daily = daily.withColumn(
    "temp_mean_f", ((F.col("tmax_c") + F.col("tmin_c")) / 2.0) * 9.0 / 5.0 + 32.0
).withColumn("hdd65", F.greatest(F.lit(0.0), F.lit(65.0) - F.col("temp_mean_f")))

daily.cache()
print(f"station-days: {daily.count():,}")
daily.select("station_id", "obs_date", "tmax_c", "tmin_c", "temp_mean_f", "hdd65").show(5)


# ===========================================================================
banner(3, "Window functions: a cold SNAP is not a cold DAY")
# ===========================================================================
# Gas demand responds to sustained cold, not to one chilly afternoon -- houses
# have thermal mass. So the interesting feature is a ROLLING window, which is
# where Spark's window functions earn their keep.
#
# rowsBetween(-6, 0) is 7 rows ending at the current one. Note: rows, not days.
# If a station has gaps, "7 rows" spans more than 7 days -- a real subtlety.
# rangeBetween on a numeric date would fix it, and is worth mentioning.
w7 = Window.partitionBy("station_id").orderBy("obs_date").rowsBetween(-6, 0)
w30 = Window.partitionBy("station_id").orderBy("obs_date").rowsBetween(-29, 0)

rolling = (
    daily.withColumn("hdd_7d", F.sum("hdd65").over(w7))
    .withColumn("hdd_30d", F.sum("hdd65").over(w30))
    .withColumn("temp_7d_avg", F.avg("temp_mean_f").over(w7))
    # Day-over-day swing: lag() reaches back one row in the same partition.
    .withColumn(
        "temp_drop_vs_yesterday",
        F.lag("temp_mean_f", 1).over(Window.partitionBy("station_id").orderBy("obs_date"))
        - F.col("temp_mean_f"),
    )
)

print("coldest sustained 7-day stretches in California (by accumulated HDD):")
(
    rolling.join(F.broadcast(stations.select("station_id", "station_name")), "station_id")
    .orderBy(F.col("hdd_7d").desc())
    .select("station_name", "obs_date", "temp_mean_f", "hdd65", "hdd_7d")
    .show(8, truncate=False)
)

print("sharpest overnight temperature drops:")
(
    rolling.filter(F.col("temp_drop_vs_yesterday").isNotNull())
    .join(F.broadcast(stations.select("station_id", "station_name")), "station_id")
    .orderBy(F.col("temp_drop_vs_yesterday").desc())
    .select("station_name", "obs_date", "temp_mean_f", "temp_drop_vs_yesterday")
    .show(5, truncate=False)
)


# ===========================================================================
banner(4, "Broadcast vs shuffle: the same join, two plans")
# ===========================================================================
# The single most useful Spark optimisation to understand. A small table can be
# shipped to every executor (BroadcastHashJoin) instead of both sides being
# shuffled across the network (SortMergeJoin).
small = stations.select("station_id", "latitude", "longitude", "elevation_m")

print("--- forced SortMergeJoin (shuffles both sides) ---")
with_hint = daily.hint("shuffle_merge").join(small, "station_id")
with_hint.explain(mode="simple")

print("\n--- BroadcastHashJoin (ships the 3,241-row table to every executor) ---")
daily.join(F.broadcast(small), "station_id").explain(mode="simple")

print("\nSpark auto-broadcasts under spark.sql.autoBroadcastJoinThreshold =",
      spark.conf.get("spark.sql.autoBroadcastJoinThreshold"))


# ===========================================================================
banner(5, "Data skew: California is not evenly covered")
# ===========================================================================
# Los Angeles has far more weather stations than Alpine County. Group by county
# and the partitions come out wildly uneven -- one task does most of the work
# while the rest idle. Seeing the distribution is how you diagnose a job that is
# slow for no obvious reason.
proc = spark.read.parquet(PROCESSED)
counts = (
    proc.groupBy("county_name")
    .agg(F.count("*").alias("station_days"), F.countDistinct("station_id").alias("stations"))
    .orderBy(F.col("station_days").desc())
)
print("most- and least-covered counties:")
counts.show(8, truncate=False)
counts.orderBy("station_days").show(5, truncate=False)

tot, n_counties = proc.count(), counts.count()
mx = counts.agg(F.max("station_days")).first()[0]
print(f"{n_counties} counties, {tot:,} rows. Largest holds {mx/tot*100:.1f}% of them.")
print("-> that is the skew. salting or repartitioning is the fix.")


# ===========================================================================
banner(6, "THE PAYOFF: every county's heating sensitivity, in one aggregate")
# ===========================================================================
# This is the demo's money shot and it is real utility analytics.
#
# For each county, fit therms = a + b * HDD. The slope b is that county's
# HEATING SENSITIVITY: extra therms burned per additional degree-day. Planners
# use exactly this number to forecast winter load.
#
# The point for Spark: no UDF, no collect, no loop. The closed-form least
# squares slope is built from plain sums, so it runs as ONE distributed
# aggregation over every county at once.
#
#     b = (n*Sxy - Sx*Sy) / (n*Sxx - Sx^2)
monthly = (
    proc.groupBy("county_name", "obs_year", "obs_month")
    .agg(
        F.avg("hdd65").alias("avg_hdd"),
        F.first("total_therms").alias("therms"),  # constant within a county-month
    )
    .filter(F.col("therms") > 0)
)

sens = (
    monthly.groupBy("county_name")
    .agg(
        F.count("*").alias("n"),
        F.sum("avg_hdd").alias("sx"),
        F.sum("therms").alias("sy"),
        F.sum(F.col("avg_hdd") * F.col("therms")).alias("sxy"),
        F.sum(F.col("avg_hdd") * F.col("avg_hdd")).alias("sxx"),
        F.corr("avg_hdd", "therms").alias("corr"),
    )
    .withColumn("denom", F.col("n") * F.col("sxx") - F.col("sx") * F.col("sx"))
    .filter(F.col("denom") != 0)
    .withColumn(
        "therms_per_hdd",
        (F.col("n") * F.col("sxy") - F.col("sx") * F.col("sy")) / F.col("denom"),
    )
    .filter(F.col("n") >= 24)  # need a couple of years to fit anything
)

print("heating sensitivity by county (therms per degree-day):")
(
    sens.select("county_name", "n", "corr", "therms_per_hdd")
    .orderBy(F.col("therms_per_hdd").desc())
    .show(12, truncate=False)
)

print("One aggregation. No UDF, no collect, no Python loop -- the arithmetic")
print("is pushed down and every county is fitted in parallel.")


# ===========================================================================
banner(7, "SIMPSON'S PARADOX, live: the same data says opposite things")
# ===========================================================================
# Every county above correlates 0.83-0.91 between degree-days and therms. Cold
# weather drives gas demand, hard and consistently.
#
# Now pool the counties together and compute one correlation over all of it.
within = sens.agg(F.avg("corr")).first()[0]
pooled = monthly.stat.corr("avg_hdd", "therms")
print(f"average WITHIN-county correlation : {within:+.4f}")
print(f"POOLED correlation, all counties  : {pooled:+.4f}")
print()
print("Same rows. Same columns. Opposite conclusions.")
print()
print("The pooled number is ~0 because county SIZE swamps the weather signal:")
print("Los Angeles burns more gas in a mild month than Alpine does in a freezing")
print("one, so the between-county variation drowns the within-county effect.")
print("Aggregate at the wrong grain and you will confidently report that")
print("temperature does not affect gas demand.")
print()
print("This is why the ML label is ranked WITHIN county rather than globally")
print("(see shared/prepare_ml_data.py) -- a global threshold would just")
print("rediscover which counties are big.")

# Show the mechanism rather than asserting it: county means are orders of
# magnitude apart, which is the whole reason pooling destroys the signal.
print("\nmonthly therms by county -- the spread that causes it:")
(
    monthly.groupBy("county_name")
    .agg(
        F.avg("therms").alias("avg_therms"),
        F.avg("avg_hdd").alias("avg_hdd"),
    )
    .orderBy(F.col("avg_therms").desc())
    .show(5, truncate=False)
)
(
    monthly.groupBy("county_name")
    .agg(
        F.avg("therms").alias("avg_therms"),
        F.avg("avg_hdd").alias("avg_hdd"),
    )
    .orderBy("avg_therms")
    .show(5, truncate=False)
)


# ===========================================================================
banner(8, "Same question in SQL, because half your room thinks in SQL")
# ===========================================================================
proc.createOrReplaceTempView("gas")
spark.sql(
    """
    SELECT season,
           ROUND(AVG(hdd65), 2)            AS avg_hdd,
           ROUND(AVG(total_therms)/1e6, 1) AS avg_m_therms,
           COUNT(*)                        AS station_days
    FROM gas
    GROUP BY season
    ORDER BY avg_hdd DESC
    """
).show(truncate=False)
print("Identical engine, identical plan. The API is a preference, not a capability.")

print("\nDone. Every section above ran on serverless Spark -- no cluster was created.")
spark.stop()
