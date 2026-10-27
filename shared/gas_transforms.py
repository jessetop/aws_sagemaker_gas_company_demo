"""
Canonical gas-demand transformation pipeline — SINGLE SOURCE OF TRUTH.

This module defines the ONE pipeline (~17 transformations) that every demo in
the series implements. Whether the learner sees it in Data Wrangler (low-code
GUI), Unified Studio Visual ETL (Glue canvas), EMR Spark, or a Unified Studio
notebook, the *logic* is identical — only the tool changes. That is the whole
pedagogical point of the series: "here is this join in Data Wrangler... here is
the same join in Visual ETL... here it is in EMR."

It uses ONLY the standard PySpark DataFrame API (no GlueContext, no SageMaker
SDK), so the exact same function runs unchanged on:
  - AWS Glue (Visual ETL backing job)
  - EMR Serverless
  - A Unified Studio / Studio notebook Spark session
  - Local PySpark (for cheap offline testing)

THE BUSINESS QUESTION
---------------------
Natural-gas demand is overwhelmingly heating-driven, so we model the question a
gas utility actually asks: *given the weather, how much gas does a county
burn?* Heating Degree Days (HDD, base 65F) is the industry-standard weather
metric for exactly this, and it falls out of daily min/max temperature.

Datasets (all open, staged by 00-setup/stage_dataset.py):
  - FACT:      NOAA GHCN-Daily station observations (Parquet, YEAR=/ELEMENT=)
  - DIMENSION: GHCN California station metadata (lat/lon/elevation)
  - DIMENSION: US Census California county centroids
  - LABEL SRC: CEC QFER natural-gas consumption, county x month x sector

Three things in this data are genuinely dirty, and each one is a transform the
learners build rather than something we pre-clean for them:
  1. GHCN `DATE` is a STRING ("20240115"), not a date.
  2. GHCN `DATA_VALUE` is an INTEGER in TENTHS of a degree C (390 = 39.0C).
  3. CEC county/agency names carry trailing whitespace, CEC months are English
     NAMES ("January"), and CEC ships up to 5 rows per county-month-sector.
"""

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

# CEC publishes the month as an English name, not a number. Mapping the name to
# an integer is a classic "map values / categorical encode" transform that every
# tool in the series exposes a little differently.
MONTH_NUMBERS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# Meteorological season labels, keyed by month number. For a gas utility the
# heating season is the part that matters — that is when demand spikes.
SEASON_LABELS = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring", 5: "Spring",
    6: "Summer", 7: "Summer", 8: "Summer",
    9: "Fall", 10: "Fall", 11: "Fall",
}

# HDD base temperature in Fahrenheit. 65F is the long-standing utility-industry
# convention: below it, buildings need heat.
HDD_BASE_F = 65.0

# The three GHCN elements the series uses.
ELEMENTS = ["TMAX", "TMIN", "PRCP"]


def _nearest_county(stations: DataFrame, counties: DataFrame) -> DataFrame:
    """Assign each station the county whose centroid is closest.

    GHCN station metadata has NO county field — only lat/lon — so the
    station-to-county mapping has to be derived. We cross-join stations against
    the 58 county centroids and keep the nearest one per station.

    Two teaching points live here:
      * A cross join is usually a mistake, but against a 58-row dimension it is
        both correct and cheap (3,241 x 58 ~ 188k pairs, computed ONCE on the
        dimension — never on the multi-million-row fact table).
      * We use squared euclidean distance on lat/lon rather than a true
        great-circle distance. Over one state it ranks neighbours identically
        and avoids the trig, but it would be wrong at continental scale. Worth
        saying out loud: approximations need their domain stated.
    """
    pairs = stations.crossJoin(
        counties.select(
            F.col("county_fips"),
            F.col("county_name"),
            F.col("county_key"),
            F.col("latitude").alias("county_lat"),
            F.col("longitude").alias("county_lon"),
        )
    ).withColumn(
        "centroid_dist",
        F.pow(F.col("latitude") - F.col("county_lat"), 2)
        + F.pow(F.col("longitude") - F.col("county_lon"), 2),
    )

    ranked = Window.partitionBy("station_id").orderBy(F.col("centroid_dist").asc())
    return (
        pairs.withColumn("_rank", F.row_number().over(ranked))
        .filter(F.col("_rank") == 1)
        .drop("_rank", "county_lat", "county_lon", "centroid_dist")
    )


def _clean_consumption(consumption: DataFrame) -> DataFrame:
    """Normalise the CEC county table into one row per county-month.

    The raw CEC export needs four separate fixes, all of them realistic:
      1. COUNTY_NAME has trailing whitespace and inconsistent case.
      2. MONTH is an English name, not a number.
      3. There are up to 5 rows per (year, month, county, sector) because CEC
         breaks consumption down further — so we must SUM, not assume one row.
         Getting this wrong silently undercounts demand by ~3x.
      4. Sector (`RNR`) is Res/Non-Res and we want both as columns, not rows.
    """
    month_expr = F.create_map(
        *[x for k, v in MONTH_NUMBERS.items() for x in (F.lit(k), F.lit(v))]
    )

    cleaned = (
        consumption.withColumn("county_key", F.upper(F.trim(F.col("COUNTY_NAME"))))
        .withColumn("obs_year", F.col("YEAR").cast("int"))
        .withColumn("obs_month", month_expr[F.trim(F.col("MONTH"))])
        .withColumn("sector", F.trim(F.col("RNR")))
        .withColumn("therms", F.col("THERMS").cast("double"))
        .filter(F.col("obs_month").isNotNull() & F.col("therms").isNotNull())
    )

    # Sum to the real grain, then pivot sector into columns.
    return (
        cleaned.groupBy("county_key", "obs_year", "obs_month")
        .pivot("sector", ["Res", "Non-Res"])
        .agg(F.sum("therms"))
        .withColumnRenamed("Res", "res_therms")
        .withColumnRenamed("Non-Res", "nonres_therms")
        .withColumn(
            "total_therms",
            F.coalesce(F.col("res_therms"), F.lit(0.0))
            + F.coalesce(F.col("nonres_therms"), F.lit(0.0)),
        )
        .filter(F.col("total_therms") > 0)
    )


def build_pipeline(
    spark: SparkSession,
    observations_path: str,
    stations_path: str,
    counties_path: str,
    consumption_path: str,
) -> DataFrame:
    """Read the raw gas/weather data and return the analytics-ready frame.

    Each numbered block below is ONE transformation a learner can point at and
    reproduce in any of the four tools. Keep them small and independently
    demoable — during teaching you show a slice, not the whole script.
    """

    # ------------------------------------------------------------------ source
    # T0. Read the four sources. Observations are columnar Parquet with Hive
    #     partitions (YEAR=/ELEMENT=); the three lookups are small CSVs with
    #     headers. In a visual tool these are the four "Source" nodes.
    obs = spark.read.parquet(observations_path)
    stations = (
        spark.read.option("header", "true").option("inferSchema", "true").csv(stations_path)
    )
    counties = (
        spark.read.option("header", "true").option("inferSchema", "true").csv(counties_path)
    )
    consumption = (
        spark.read.option("header", "true").option("inferSchema", "true").csv(consumption_path)
    )

    # T1. Standardize column names. Raw GHCN columns are SHOUTED and cryptic
    #     (ID, DATA_VALUE, Q_FLAG). Rename to snake_case so every downstream
    #     step — and every tool — refers to the same names.
    obs = (
        obs.withColumnRenamed("ID", "station_id")
        .withColumnRenamed("DATE", "obs_date_raw")
        .withColumnRenamed("DATA_VALUE", "value_tenths")
        .withColumnRenamed("ELEMENT", "element")
        .withColumnRenamed("Q_FLAG", "quality_flag")
        .withColumnRenamed("M_FLAG", "measurement_flag")
        .withColumnRenamed("S_FLAG", "source_flag")
    )

    # T2. Drop rows missing the fields the whole pipeline depends on. (In Data
    #     Wrangler this is "Handle missing -> Drop rows"; in Visual ETL it is a
    #     "Drop Null Fields" / Filter node.)
    obs = obs.dropna(subset=["station_id", "obs_date_raw", "value_tenths"])

    # T2b. FILTER TO CALIFORNIA BEFORE ANYTHING EXPENSIVE.
    #
    #      GHCN is a global dataset: ten years of three elements is on the order
    #      of 200 million rows, and California is about 5% of that. The pivot in
    #      T7 is a wide shuffle, so doing it first and joining the station
    #      dimension afterwards would shuffle 200M rows in order to discard 190M
    #      of them.
    #
    #      A semi-join against the 3,241-row station list is a broadcast join —
    #      no shuffle at all — and it cuts the data ~20x before the first
    #      expensive step. Same answer, less work.
    #
    #      MEASURED, so the comment does not oversell it: on 10 years of data
    #      this took the Glue run from 643s/$0.3144 to 597s/$0.2919 — about 7%,
    #      with byte-identical output. Not the landslide it looks like it should
    #      be, because the pivot was never the bottleneck: both versions still
    #      scan all 201M rows off S3, and that I/O dominates.
    #
    #      Which makes this the best measurement lesson in the series rather
    #      than the best optimisation one. The change is right and worth
    #      keeping; the point to teach is that the obvious fix returned 7%
    #      because the real cost was elsewhere. Partition pruning — reading
    #      only the YEAR=/ELEMENT= partitions you actually need — buys far more
    #      here than anything you do to the shuffle. See TEST_LOG.md.
    obs = obs.join(
        F.broadcast(stations.select("station_id")), on="station_id", how="inner"
    )

    # T3. Parse the date. GHCN stores it as the STRING "20240115", so this is a
    #     real parse, not a cast.
    #     NOTE: we pass an explicit format to to_date() rather than relying on
    #     an implicit cast. Spark 3.x under the CORRECTED time parser will
    #     return NULL for an unparseable string instead of raising, so a silent
    #     cast here would quietly delete rows. The same class of cross-engine
    #     portability trap as a direct timestamp cast across Spark versions — worth
    #     calling out in class.
    obs = obs.withColumn(
        "obs_date", F.to_date(F.col("obs_date_raw").cast("string"), "yyyyMMdd")
    ).filter(F.col("obs_date").isNotNull())

    # T4. Quality filter. GHCN sets Q_FLAG only when a reading FAILED one of its
    #     quality-control checks, so "good data" means the flag is null/blank.
    #     This is the analogue of a "keep only real transactions
    #     only" filter: drop records the source itself distrusts.
    obs = obs.filter(
        F.col("quality_flag").isNull() | (F.trim(F.col("quality_flag")) == "")
    )

    # T5. Rescale to real units. GHCN temperatures are integers in TENTHS of a
    #     degree C and precipitation in tenths of a mm. Forgetting this is the
    #     single easiest way to get a plausible-but-10x-wrong answer.
    obs = obs.withColumn("value_scaled", F.col("value_tenths") / 10.0)

    # T6. Drop physically implausible readings before they poison the pivot.
    obs = obs.filter(
        ~(F.col("element").isin("TMAX", "TMIN"))
        | ((F.col("value_scaled") >= -50) & (F.col("value_scaled") <= 60))
    ).filter(~(F.col("element") == "PRCP") | (F.col("value_scaled") >= 0))

    # T7. RESHAPE: pivot one-row-per-(station, day, element) into one row per
    #     station-day with TMAX/TMIN/PRCP as columns. This is the headline
    #     "reshape your data" step and the main reason this pipeline wants
    #     Spark — it is a wide shuffle over millions of rows.
    daily = (
        obs.groupBy("station_id", "obs_date")
        .pivot("element", ELEMENTS)
        .agg(F.first("value_scaled"))
        .withColumnRenamed("TMAX", "temp_max_c")
        .withColumnRenamed("TMIN", "temp_min_c")
        .withColumnRenamed("PRCP", "precip_mm")
    )

    # T8. A station-day is only usable for HDD if BOTH bounds are present.
    daily = daily.filter(
        F.col("temp_max_c").isNotNull() & F.col("temp_min_c").isNotNull()
    ).filter(F.col("temp_max_c") >= F.col("temp_min_c"))

    # T9. Derive the mean temperature in Fahrenheit and the diurnal range.
    #     Demonstrates a calculation combining two columns plus a unit change.
    daily = daily.withColumn(
        "temp_mean_f",
        ((F.col("temp_max_c") + F.col("temp_min_c")) / 2.0) * 9.0 / 5.0 + 32.0,
    ).withColumn("temp_range_c", F.col("temp_max_c") - F.col("temp_min_c"))

    # T10. Derive HEATING DEGREE DAYS (base 65F) — the domain metric this whole
    #      demo exists to explain. hdd = max(0, 65 - mean_temp_F). A warm day
    #      contributes zero, which is why gas demand is floored in summer.
    daily = daily.withColumn(
        "hdd65", F.greatest(F.lit(0.0), F.lit(HDD_BASE_F) - F.col("temp_mean_f"))
    )

    # T11. Extract calendar features from the observation date: year, month,
    #      day-of-week name, and a weekend flag (commercial gas load drops at
    #      weekends, so this is a genuinely predictive feature).
    daily = (
        daily.withColumn("obs_year", F.year("obs_date"))
        .withColumn("obs_month", F.month("obs_date"))
        .withColumn("obs_dow", F.date_format("obs_date", "EEEE"))
        .withColumn("is_weekend", F.dayofweek("obs_date").isin(1, 7))
    )

    # T12. Map the month number to a season label. Build the CASE expression
    #      from the shared dictionary so the mapping is identical everywhere.
    season_col = F.lit("Unknown")
    for month, label in SEASON_LABELS.items():
        season_col = F.when(F.col("obs_month") == month, F.lit(label)).otherwise(season_col)
    daily = daily.withColumn("season", season_col)

    # T13. Bucket HDD into categorical bands. Classic "bin a numeric column"
    #      transform, and the bands are how utilities actually talk about days.
    daily = daily.withColumn(
        "hdd_bucket",
        F.when(F.col("hdd65") < 1, "none")
        .when(F.col("hdd65") < 10, "mild")
        .when(F.col("hdd65") < 25, "moderate")
        .when(F.col("hdd65") < 40, "cold")
        .otherwise("severe"),
    )

    # T14. Flag the heating season (November-March). Combines a derived calendar
    #      column into a single boolean feature.
    daily = daily.withColumn(
        "is_heating_season", F.col("obs_month").isin(11, 12, 1, 2, 3)
    )

    # T15. JOIN the station dimension, which is itself enriched with its nearest
    #      county — so this is a join of a join. This is the headline "join two
    #      datasets" step every tool demonstrates.
    #
    #      Note this join is pure ENRICHMENT, not filtering: T2b already
    #      restricted the data to California stations. It is still an inner join
    #      so that a station present in the observations but missing from the
    #      dimension cannot silently produce null counties downstream.
    station_counties = _nearest_county(stations, counties)
    enriched = daily.join(
        F.broadcast(
            station_counties.select(
                "station_id",
                "station_name",
                "elevation_m",
                "latitude",
                "longitude",
                "county_fips",
                "county_name",
                "county_key",
            )
        ),
        on="station_id",
        how="inner",
    )

    # T16. JOIN the CEC consumption table on county + year + month to attach the
    #      therms actually burned. Note the grain change: weather is DAILY,
    #      consumption is MONTHLY, so every day in a county-month carries the
    #      same therms value. That is a real property of the data and it has
    #      consequences for how you split train/test — see add_ml_label().
    monthly = _clean_consumption(consumption)
    enriched = enriched.join(
        monthly, on=["county_key", "obs_year", "obs_month"], how="inner"
    )

    # T17. Final projection: keep the analytics-ready columns in a sensible
    #      order and drop the raw intermediates. (In a visual tool this is the
    #      final "Change Schema" / "Select Fields" node before the target.)
    final = enriched.select(
        "obs_date",
        "obs_year",
        "obs_month",
        "obs_dow",
        "season",
        "is_weekend",
        "is_heating_season",
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "elevation_m",
        "county_fips",
        "county_name",
        "county_key",
        "temp_max_c",
        "temp_min_c",
        "temp_mean_f",
        "temp_range_c",
        "precip_mm",
        "hdd65",
        "hdd_bucket",
        "res_therms",
        "nonres_therms",
        "total_therms",
    )

    return final


def add_ml_label(df: DataFrame) -> DataFrame:
    """Optional T18 used by the ML modules (Feature Store / Training / Tuning).

    Adds a binary target `high_demand`: 1 when this county-month's total therms
    sits in the top quartile *for that county*. This turns the cleaned dataset
    into a supervised classification problem reused by the training, tuning, and
    deployment demos downstream.

    Two deliberate design choices worth teaching:

      * We rank WITHIN each county, not globally. A global threshold would just
        rediscover that Los Angeles is bigger than Alpine — the model would
        score well and teach nothing. Ranking within county forces it to learn
        the weather signal instead.

      * The label is derived from CONSUMPTION, never from the weather columns.
        If you labelled cold days as "high demand" the model would be learning
        its own input and the AUC would be a lie.

    Known caveat — GROUP STRUCTURE: consumption is monthly, so every day in a
    county-month shares one label. Do NOT split train/test randomly or the same
    county-month lands on both sides and the score is inflated. Split by
    county-month (see shared/prepare_ml_data.py). This is the gas series'
    classic leak-by-aggregation, and a better lesson than a contrived one.
    """
    by_county = Window.partitionBy("county_key").orderBy(F.col("total_therms").asc())
    return df.withColumn("_pct", F.percent_rank().over(by_county)).withColumn(
        "high_demand", (F.col("_pct") > 0.75).cast("int")
    ).drop("_pct")
