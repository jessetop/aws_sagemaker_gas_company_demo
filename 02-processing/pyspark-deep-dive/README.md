# PySpark deep dive — gas demand, no EMR cluster

A genuinely interesting PySpark notebook on the gas-utility dataset, deliberately
built **without an EMR cluster**.

## Why not EMR

The AWS lab already covers "here is how you connect Studio to an EMR cluster and
it does some stuff." Repeating that teaches nothing extra, and it carries the one
risk this repo takes seriously: a cluster somebody forgets about.

So this demo is about the **DataFrame work** instead — windows, pivots, join
strategy, skew, and a real utility metric computed as a single distributed
aggregation. The Spark engine is identical. Only the thing we point at changes.

## Where to run it, cheapest first

| Option | Cluster? | Cost for a 5-min demo | Good for |
|---|---|---|---|
| **Glue Interactive Sessions** | none | ~**$0.07** | **the live demo** |
| Glue job (`run_spark_analysis.py`) | none | ~$0.30 full run | verifying the code |
| EMR Serverless | none (app only) | similar | if you want EMR branding |
| EMR cluster | **yes** | $$$ and easy to forget | the AWS lab, not this |

Glue Interactive Sessions bill **per second** with a one-minute minimum and no
cluster to tear down. Set an idle timeout anyway — an idle session still bills
until it expires:

```python
%idle_timeout 15
%glue_version 4.0
%worker_type G.1X
%number_of_workers 4
```

Those magics go in the first cell of the notebook. `%idle_timeout 15` is the
line that stops this becoming another Canvas story.

## Files

| File | What it is |
|---|---|
`gas_spark_analysis.py` | **The source of truth.** Every notebook cell, as a runnable script. |
`run_spark_analysis.py` | Runs the above as a Glue job, waits, reports DPU cost. |

The script exists *first*, on purpose: it gets run on real Glue so every section
is proven before anyone opens the notebook in front of a room. A notebook full
of unverified PySpark is exactly what dies on stage.

```bash
python 02-processing/pyspark-deep-dive/run_spark_analysis.py --start
python 02-processing/pyspark-deep-dive/run_spark_analysis.py --logs
```

## What the seven sections teach

1. **Partition pruning is free performance — if you ask for it.**
   The data is `YEAR=`/`ELEMENT=` partitioned. Filter on a partition column and
   Spark never opens those directories. The explain plan *proves* it:
   `PartitionFilters` means skipped, `PushedFilters` means it still read
   everything. Showing the plan beats asserting the claim.

2. **Long to wide.** GHCN is one row per station/day/measurement; almost every
   question needs it wide. `groupBy().pivot()`, and naming the pivot values
   explicitly so Spark doesn't run a separate job just to discover them.

3. **Window functions: a cold *snap* is not a cold *day*.**
   Houses have thermal mass, so demand responds to sustained cold. Rolling 7-
   and 30-day HDD with `rowsBetween`, plus `lag()` for overnight temperature
   drops. The subtlety worth raising: `rowsBetween(-6, 0)` is seven *rows*, not
   seven days — with gaps in a station's record those differ, and `rangeBetween`
   is the fix.

4. **Broadcast vs shuffle: the same join, two plans.**
   The most useful Spark optimisation to actually understand. Run it both ways
   and diff the plan: `BroadcastHashJoin` ships 3,241 station rows to every
   executor; `SortMergeJoin` shuffles both sides across the network.

5. **Data skew: California is not evenly covered.**
   Los Angeles has far more stations than Alpine. Group by county and one task
   does most of the work while the rest idle. This is why a job is sometimes
   slow for no visible reason, and seeing the distribution is the diagnosis.

6. **The payoff — every county's heating sensitivity, in one aggregate.**
   Fit `therms = a + b·HDD` per county. The slope *b* is therms burned per extra
   degree-day, which is the number utility planners actually forecast winter
   load with.

   The Spark lesson: the closed-form least-squares slope is built from plain
   sums, so there is **no UDF, no `collect()`, no Python loop**. Every county is
   fitted simultaneously in one distributed aggregation. This is the difference
   between using Spark and using Spark *well*.

7. **The same question in SQL,** because half the room thinks in SQL. Identical
   engine, identical plan — the API is a preference, not a capability.

## The 5-minute version

You cannot do all seven in five minutes. Do **1, 4, and 6**:

- **(1) partition pruning** — the explain plan, 60 seconds. Concrete and visual.
- **(4) broadcast vs shuffle** — two plans side by side, 90 seconds. The single
  most transferable thing in the notebook.
- **(6) heating sensitivity** — 2 minutes, and it is *their* business metric
  falling out of one aggregation.

Leave sections 2, 3, 5 and 7 in the notebook as the thing they take away. "The
rest of this notebook is yours" is a good closing line and it makes the artifact
worth keeping.

## Cost discipline

```python
%idle_timeout 15      # first cell, every time
```

When you're done:

```bash
# confirm nothing Spark-shaped is still alive
python cleanup/verify_teardown.py
```

An interactive session is not caught by the Canvas reaper — that only reaps
SageMaker apps. The idle timeout is your guard here, so set it.
