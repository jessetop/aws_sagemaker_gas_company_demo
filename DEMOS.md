# The 5-minute demos — SoCalGas data, one service at a time

Instructor-led demos on **our** dataset. These are deliberately **not** the AWS
labs: the labs are self-contained and the students run those themselves. This is
"here is your own data, in this service" — the thing that makes the client lean
in, because it is their problem on screen instead of abalone or Titanic.

Each demo is five minutes and follows the same shape.

---

## The cooking-show pattern

Every one of these demos is structured the same way, because the alternative is
watching a progress bar on stage:

> **1. Here's how you make it.** Open the console, configure the thing, let them
> see the knobs and what you'd fill in.
>
> **2. Hit cancel.** Out loud: *"this takes twelve minutes, so I'm not going to
> make you watch it."* Cancel, or just navigate away.
>
> **3. Here's one I made earlier.** Cut to the finished artifact and spend the
> remaining three minutes on the **result** — which is the part that actually
> teaches anything.

The cakes are baked by:

```bash
python shared/prebake_demos.py --all      # ~46 min, a few dollars, unattended
python shared/prebake_demos.py --status   # confirm before class
```

Run `--status` the morning of. If anything says `no`, bake it before you walk in.

### Two rules

- **Never demo an unbaked artifact.** `--status` must be green for the demo
  you're about to give.
- **Say "here's one I made earlier" out loud.** Pretending a 4-second load was
  a live 12-minute job is the one thing that will cost you the room's trust if
  somebody spots the timestamp.

---

## The spine: one dataset, one sentence

Say this once at the start of the day and refer back to it all day.

> *"SoCalGas's load is driven by the weather. We took every weather observation
> on earth for the last ten years — two hundred million rows — narrowed it to
> California's three thousand stations, worked out how cold each county actually
> got, and lined that up against how much gas each county burned."*

```
201,486,363 raw worldwide rows  →  1,668,673 California station-days

                         mean therms   mean HDD
outside heating season      35.1 M       3.02
in heating season           49.6 M      14.24
```

41% more gas, 4.7× the heating degree days. **That relationship is the product.**
Every demo below is one tool looking at that same data.

---

## Demo 1 — SageMaker Studio itself (5 min)

**Slot:** pairs with Module 1 Setup.
**Baked:** nothing needed.

1. Open the domain. Show the left nav — "everything we'll touch today is in here."
2. Open the S3 bucket: `raw/observations/` with `YEAR=`/`ELEMENT=` partitions,
   `raw/stations/`, `raw/counties/`, `raw/consumption/`.
3. Point at `processed/visual-etl/` partitioned by `obs_year`/`obs_month`.

**The line:** *"Raw public data in, analytics-ready gas demand out. That arrow is
the whole course."*

**Worth 30 seconds:** the cost guard. *"Canvas bills about fifty dollars a day
and keeps billing after you close the tab. We left one running after a class in
June — two hundred dollars. So there's a Lambda that kills idle Canvas sessions
every hour. Build that before you build anything else."* Instructors feel this
one.

---

## Demo 2 — Data Wrangler (5 min)

**Slot:** Module 2, Data Processing.
**Baked:** `data` (the processed output is the "already finished" artifact).

⚠️ **Data Wrangler is inside Canvas now.** In the modern Studio experience
Studio Classic is gone — Data Wrangler is reached through SageMaker Canvas. That
means this demo starts a **billable Canvas session**. Run
`powershell -File cleanup/kill_canvas.ps1` when you're done; the reaper is a
backstop, not an excuse.

**Here's how you make it:**

1. Canvas → Data Wrangler → Import → S3 → `raw/observations/`.
2. Let it profile. Show the inferred schema and point at what's wrong with it:
   - `DATE` is a **string**, `"20240115"`
   - `DATA_VALUE` is an **integer in tenths of a degree C** — `390` is 39.0 °C
   - `Q_FLAG` is populated only when a reading **failed** quality control
3. Run **Data Quality and Insights**. One click, and it is the single most
   impressive thing in the product — distributions, missing values, outliers,
   on real client data.
4. Add two transforms live so they see the no-code loop: rename `DATA_VALUE`,
   then a custom formula `value_tenths / 10`.
5. Click **Export → S3**.

**Hit cancel:** *"That spins up a Spark job for a few minutes. Let's skip ahead."*

**Here's one I made earlier:** open `processed/visual-etl/` and show the finished
25-column table — real county names, `hdd65`, `hdd_bucket`, therms joined on.

> **One-time setup job for you:** build this flow once in Canvas and use
> **Export → flow file**, then commit it to
> `01-data-prep/old-data-wrangler/`. The flow JSON in the repo today is a
> three-node stub and should not be imported live. Hand-writing that JSON is not
> safe — the operator schema is version-specific and a flow that fails to import
> on stage is worse than no flow at all.

---

## Demo 3 — PySpark, serverless (5 min)

**Slot:** Module 2, after Data Wrangler.
**Baked:** `data`.
**Runs on:** Glue Interactive Sessions — **no EMR cluster**, ~$0.07 for a
5-minute demo, per-second billing, nothing to tear down.

Full detail: [`02-processing/pyspark-deep-dive/README.md`](02-processing/pyspark-deep-dive/README.md)

**Why not EMR:** the AWS lab already does "here's how you connect Studio to an
EMR cluster and it runs some stuff." Repeating that teaches nothing extra and
risks leaving a cluster running. So this demo is about the **DataFrame work**,
which is the part the labs skip — and the Spark engine is identical either way.

First cell, every time:

```python
%idle_timeout 15
%glue_version 4.0
%worker_type G.1X
%number_of_workers 4
```

`%idle_timeout 15` is the line that stops this becoming another Canvas story.
The Canvas reaper does **not** catch Glue sessions — it only reaps SageMaker
apps.

**Do three of the seven sections. These three:**

1. **Partition pruning** (60s). Filter on `YEAR`/`ELEMENT`, show the explain
   plan. `PartitionFilters` means those directories were never opened;
   `PushedFilters` would mean it read everything anyway. Proving it beats
   claiming it.
2. **Broadcast vs shuffle** (90s). Same join, two plans side by side.
   `BroadcastHashJoin` ships 3,241 station rows to every executor;
   `SortMergeJoin` shuffles 1.67M rows across the network. The most
   transferable 90 seconds in the course.
3. **Heating sensitivity** (2 min) — **the money shot.** Fit
   `therms = a + b·HDD` per county; the slope is therms per extra degree-day,
   which is what planners forecast winter load with.

   > *"No UDF, no collect, no Python loop. The least-squares slope is just sums,
   > so every county gets fitted at once in a single distributed aggregation.
   > That's the difference between using Spark and using Spark well."*

**Closing line:** *"The rest of this notebook is yours"* — rolling windows,
`lag()` for overnight temperature drops, the long-to-wide pivot, skew diagnosis,
and the same query in SQL. Makes the artifact worth keeping.

## Demo 4 — SageMaker Processing (5 min)

**Slot:** Module 2, Lab 4 territory.
**Baked:** `splits`.
**Status:** ⚠️ not yet ported — `08-pipelines/preprocess.py` is still taxi schema.

**Here's how you make it:** show `shared/prepare_ml_data.py` — a plain Python
script, no SageMaker imports in the data logic. Then show how a Processing job
wraps it: container + instance + input/output channels.

**The line:** *"Processing is for when your transform is just code. No canvas, no
cluster — hand SageMaker a script and a container and it runs it on whatever
size machine you ask for."*

**Here's one I made earlier:** `ml/gas/train/`, `validation/`, `test/` in S3.
150,000 rows, 19 features, label first.

**Worth 60 seconds — the honest bit:** this script is where the two real data
traps live.

- **Group leakage.** CEC consumption is *monthly*, so every daily row in a
  county-month carries the same label. Split rows at random and the same
  county-month lands on both sides — the model sees its test labels during
  training. We split by county-month group. `--random-split` reproduces the
  inflated score if you want to show the gap.
- **47% of rows have no precipitation reading.** Many GHCN stations report
  temperature but not rainfall. A null means "no gauge", not "no rain" — so we
  impute zero *and* add a `precip_reported` flag, rather than throwing away half
  the dataset.

---

## Demo 5 — Feature Store (5 min)

**Slot:** Module 2, Feature Store section.
**Baked:** `features`.

**Here's how you make it:** show `03-feature-store/feature_store_ingest.py` —
feature definitions, record identifier, event time, online vs offline store.

**Hit cancel:** ingestion takes a couple of minutes.

**Here's one I made earlier:** Feature Store → `roi-smdemo-gas-features`. Show
the schema, then the offline store sitting in S3 as Parquet.

**The line:** *"Right now one team computes heating degree days. Next month
another team needs it and writes their own slightly different version. Feature
Store is how `hdd65` gets computed once and consumed by everyone — with the same
definition at training time and at inference time."*

That last clause is the whole product. Training/serving skew is the bug Feature
Store exists to prevent.

---

## Demo 6 — Training jobs (5 min)

**Slot:** Module 3 / Day 2 Module 4 lead-in.
**Baked:** `training`.

**Here's how you make it:** `04-training/launch_training.py`. Show the Estimator:
entry point, instance type, hyperparameters. Then show `train.py` and the
SageMaker contract — `SM_CHANNEL_TRAIN`, `SM_MODEL_DIR`, and metrics printed as
`name=value` to stdout.

**Hit cancel:** *"Three minutes to provision, train, and upload. Skipping."*

**Here's one I made earlier:** Training jobs → the completed job. Point at:
- 145 billable seconds
- `validation_accuracy=0.8794`, `validation_auc=0.9235` scraped from stdout
- the model artifact in S3

**Then do the thing that earns respect** — see Demo 7.

---

## Demo 7 — Experiments, and the honest metric (5 min)

**Slot:** right after training. **This is the best demo you have.**
**Baked:** `training`, `tuning`.

**Here's one I made earlier:** Experiments → compare the runs. Baseline plus the
HPO trials, each with its hyperparameters and final metrics.

Then run the arc. It takes three minutes and it is worth more than any feature
tour in the course:

| | AUC |
|---|---|
| all features | **0.9235** |
| calendar only (`obs_month`, `season_*`, `is_heating_season`) | 0.9043 |
| weather only | 0.8298 |
| **deseasonalised label** | **0.5159** |

> *"We got 0.92 and we were delighted. Then we looked at feature importance:
> seventy percent of the model was one column — is it winter. So we asked the
> harder question — was* this *January unusual for this county — and the model
> fell to a coin flip. The model wasn't bad. The question was easy, and we
> didn't notice until we checked."*

Then land the diagnosis: **the label is a county-month aggregate, the features
are a single station-day.** The grain doesn't match. One day's weather can't
tell you whether a whole month was anomalous.

Reproduce it live if you have time:

```bash
python shared/prepare_ml_data.py --no-calendar      # 0.92 -> 0.83
python shared/prepare_ml_data.py --deseasonalize    # -> 0.52
```

**Why this demo works:** every data scientist in the room has shipped a metric
they didn't interrogate. Watching someone catch their own is more useful than
watching a model win.

---

## Demo 8 — Hyperparameter tuning (5 min)

**Slot:** Module 3.
**Baked:** `tuning`.

**Here's how you make it:** the tuner — search space, objective
`validation:auc`, max jobs, max parallel. *"Max parallel is a cost dial, not a
speed dial."*

**Hit cancel:** fifteen minutes for four jobs.

**Here's one I made earlier:** the tuning job's leaderboard, best trial
highlighted. Point out how little the objective moved between trials — *"on this
problem the hyperparameters barely matter, because the signal is in the label
definition, not the model. Tuning is the last thing you should reach for, not
the first."*

---

## Demo 9 — Clarify: bias and explainability (5 min)

**Slot:** Module 3, Design/Governance.
**Baked:** `clarify`.

**Here's how you make it:** `clarify_bias_explainability.py` — facet column,
label values, SHAP baseline.

**Hit cancel:** SHAP runs the model thousands of times behind a shadow endpoint.

**Here's one I made earlier:** open `report.html` from S3. Show the bias metrics
on the `is_heating_season` facet, then the SHAP feature attributions.

**The gas-specific line:** *"Clarify's facet here is heating season, and the
report says the model behaves very differently in winter than in summer. For a
utility that matters: a demand model that's only accurate half the year is a
model that fails exactly when you need it."*

**Cost warning worth passing on:** SHAP cost scales with rows × samples. Run it
on the full test set and you get millions of inferences through a shadow
endpoint. We sample 300 rows.

---

## Demo 10 — Deployment and inference (5 min)

**Slot:** Day 2, Module 4.
**Baked:** nothing — this one runs live, and should.

This is the exception to the cooking show. `deploy_and_infer.py` creates an
endpoint, sends three inferences, and **deletes the endpoint** in one pass. It's
quick enough to run for real, and watching the endpoint go away is the point.

```bash
python 07-deployment/deploy_and_infer.py
```

**The line:** *"An endpoint bills by the hour from the moment it's InService,
whether or not anyone calls it. Notice the last line of this script is a delete."*

---

## Demo 11 — Autopilot / Canvas (5 min)

**Slot:** wherever AutoML fits.
**Baked:** run `09-autopilot/launch_autopilot.py` ahead of time (not yet in the
prebake list — it takes ~30 min).

**The framing that lands:** Autopilot is the *engine*; there are three front
doors — SDK (code), Studio UI (low-code), Canvas (no-code). Same ranked
leaderboard out of all three.

**Here's one I made earlier:** the candidate leaderboard.

⚠️ Canvas session — kill it afterwards.

---

## Readiness

Check before you commit to a demo in a running class.

| # | Demo | Code | Artifact baked | Safe to demo |
|---|---|---|---|---|
| 1 | Studio tour | n/a | n/a | ✅ |
| 2 | Data Wrangler | ⚠️ flow is a stub | ✅ data | ⚠️ live-build only |
| 3 | Spark on EMR | ❌ not ported | ✅ data | ❌ |
| 4 | SageMaker Processing | ⚠️ partial | ✅ splits | ⚠️ talk-through |
| 5 | Feature Store | ✅ verified | ✅ `roi-smdemo-gas-features` | ✅ |
| 6 | Training | ✅ verified | ✅ | ✅ |
| 7 | Experiments + metric arc | ✅ verified | ✅ baseline + 4 HPO trials | ✅ |
| 8 | HPO | ✅ verified | ✅ `roi-smdemo-gas-hpo-261026-1514` | ✅ |
| 9 | Clarify | ✅ ported | see `--status` | check |
| 10 | Deployment | ✅ ported | live | ⚠️ run once first |
| 11 | Autopilot | ✅ ported | not baked | ❌ |

### Two AWS API traps the prebaker had to work around

Both produce *silently wrong* answers rather than errors, and both would send
you into a class mistrusting a correct `--status`.

1. **`MaxResults` is applied before `NameContains`.** This returns zero:
   ```
   list_training_jobs(NameContains="roi-smdemo-gas-train",
                      StatusEquals="Completed", MaxResults=1)   -> 0 results
   list_training_jobs(NameContains="roi-smdemo-gas-train",
                      StatusEquals="Completed")                 -> 1 result
   ```
   SageMaker fetches one job, *then* filters it. The moment an HPO trial became
   the newest job in the account, `--status` started reporting the training job
   as missing when it was sitting right there. Never combine `MaxResults` with a
   name filter — filter, then sort.

2. **`--max-items` appends a pagination token to `--output text`** (AWS CLI).
   A query for one timestamp returns the value, then `None` on its own line.
   Use the API's own `--limit` and strip to digits.

### Backlog, in the order I'd do it

1. **Export a real Data Wrangler flow** from Canvas and commit it. Demo 2 is the
   first one the room sees in Module 2 and it's currently live-build-only.
2. **Port module 2 (EMR)** — Demo 3 is the only one with no working code.
3. **Port `08-pipelines/preprocess.py`** — makes Demo 4 a real Processing job
   rather than a talk-through, and unblocks Pipelines.
4. **Run Demo 10 once offline** before trusting it live.
5. **Add Autopilot to the prebake list.**
