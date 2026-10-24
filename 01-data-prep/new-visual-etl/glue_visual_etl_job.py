"""
Unified Studio "Visual ETL" backing job (the NEW way).

In SageMaker Unified Studio you build this pipeline on a drag-and-drop canvas:
a Source node for the GHCN observations Parquet, Source nodes for the station /
county / consumption lookups, transform nodes (Filter, Derived column, Pivot,
Join, Change Schema...), and a Target node. The canvas then GENERATES a Glue
Spark job exactly like this one.

We keep the heavy transformation logic in the shared `gas_transforms` module so
the SAME logic the EMR and notebook demos use also backs the visual job. On the
canvas, the equivalent of importing this module is a single "Custom transform"
node; most of the individual steps (Filter, Join, Derived columns) can also be
expressed as their own visual nodes — which is exactly what you demo live.

Job parameters (passed by Unified Studio / Glue as --KEY value):
  --JOB_NAME          (supplied automatically by Glue)
  --observations_path  s3://.../raw/observations/
  --stations_path      s3://.../raw/stations/ghcnd_stations_ca.csv
  --counties_path      s3://.../raw/counties/ca_county_centroids.csv
  --consumption_path   s3://.../raw/consumption/cec_ng_county_monthly.csv
  --output_path        s3://.../processed/visual-etl/
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

# The shared pipeline is shipped to the job via --extra-py-files, so it is
# importable here just like any local module.
from gas_transforms import build_pipeline

# Glue injects these arguments; getResolvedOptions parses them from sys.argv.
args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "observations_path",
        "stations_path",
        "counties_path",
        "consumption_path",
        "output_path",
    ],
)

# GlueContext wraps a SparkContext and is what the visual canvas uses under the
# hood. We only need the plain SparkSession from it to run our DataFrame logic.
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

# GHCN DATE is the string "20240115". Spark 3's CORRECTED parser is strict about
# this; LEGACY would silently coerce odd values instead of returning NULL. We
# want the strict behaviour so bad rows are visibly dropped in T3 rather than
# quietly mangled.
spark.conf.set("spark.sql.legacy.timeParserPolicy", "CORRECTED")

# ---- The pipeline: identical to every other demo in the series -------------
raw_count = spark.read.parquet(args["observations_path"]).count()
print(f"[visual-etl] raw observations (worldwide, all elements) = {raw_count}")

result = build_pipeline(
    spark,
    args["observations_path"],
    args["stations_path"],
    args["counties_path"],
    args["consumption_path"],
)

row_count = result.count()  # forces execution; handy to print for the demo
print(f"[visual-etl] transformed row count = {row_count}")
print(f"[visual-etl] reduction: {raw_count} raw -> {row_count} California station-days")
result.show(5, truncate=False)

# A couple of cheap sanity aggregates worth showing on screen: gas demand should
# track heating degree days, and that relationship is the whole point.
print("[visual-etl] rows per HDD bucket:")
result.groupBy("hdd_bucket").count().orderBy("count", ascending=False).show(truncate=False)
print("[visual-etl] mean therms by heating season:")
result.groupBy("is_heating_season").avg("total_therms", "hdd65").show(truncate=False)

# Target node: write the analytics-ready table as partitioned Parquet.
# Partitioned by year+month rather than the full date: a single month of
# California station-days is a sensible file size, whereas partitioning by day
# would emit thousands of tiny files.
(
    result.write.mode("overwrite")
    .partitionBy("obs_year", "obs_month")
    .parquet(args["output_path"])
)
print(f"[visual-etl] wrote results to {args['output_path']}")

job.commit()
