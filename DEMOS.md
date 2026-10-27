# The 5-minute demos — gas-utility data, one service at a time

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
python 00-setup/create_bucket.py          # once, ever
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

> *"a gas utility's load is driven by the weather. We took every weather observation
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

## Demo 2 — Data Wrangler: catching your own leak (5 min)

**Module 2, first tool** · **Baked:** two flows, both pre-run
**Verified:** F1 **1.0** -> **0.675**

> ⚠️ Billable Canvas session. `powershell -File cleanup/kill_canvas.ps1` after.

### The two cakes

Import both before class and run the Quick Model in each, so both results are
already sitting there:

| Flow | S3 | Quick Model result |
|---|---|---|
`gas_demand.flow` | `s3://<bucket>/flows/gas_demand.flow` | **F1 = 1.0** + leakage warning |
`gas_demand_no_leak.flow` | `s3://<bucket>/flows/gas_demand_no_leak.flow` | **F1 = 0.675** |

Both are 6-8 nodes: GHCN TMAX source -> infer types -> custom pandas (the
cleaning) -> join to the CA stations CSV -> Quick Model. The second adds a
**Drop column** on `temp_max_c` before the model.

### Beat 1 - the data is a mess, and that's the point (90s)

Open flow 1 at the **infer types** node. Three traps in a seven-column table:

| Column | The trap |
|---|---|
`DATE` | a **string**, `"20240115"` |
`DATA_VALUE` | integer in **tenths of a degree C** - `390` is 39.0 C |
`Q_FLAG` | set **only when a reading failed** quality control |

> *"Miss the tenths and every number you produce is plausible and ten times
> wrong. This is what real public data looks like."*

Then the **clean GHCN** node - all four fixes as commented pandas.

### Beat 2 - the target (30s)

> *"Sixty-five Fahrenheit is the utility industry's heating base. If the day's
> HIGH never got there, the utility had to supply gas for it. That's our label:
> `heating_day`."*

### Beat 3 - F1 of 1.0, and why that's bad news (90s)

Open the Quick Model analysis.

> *"F1 of one-point-zero. Perfect. Who's suspicious?"*

Then read Canvas's own warning aloud:

> *"The feature temp_max_c predicted the target with more than 0.95 prediction
> power, which often indicates an error called Target leakage."*

> *"The tool caught me. I defined heating_day AS temp_max_c below 18.33, then
> left temp_max_c in the features. The model isn't predicting anything - it's
> reading the answer off its own input."*

Honesty plays well here: this was a genuine mistake, found by the product.

### Beat 4 - here's one I made earlier (90s)

Switch to `gas_demand_no_leak.flow`. One extra node: Drop column on
`temp_max_c`.

> **F1 = 0.675**

Remaining features: `obs_month`, `latitude`, `longitude`, `elevation_m`.

> *"Zero point six seven five. That's a real number. The question is now
> genuinely interesting - can where you are and what month it is tell you
> whether the gas had to flow? Substantially, yes. Not perfectly. And that gap
> is where the actual modelling work lives."*

### The through-line to set up Demo 7

> *"Data Wrangler caught that leak automatically because it was blatant - one
> column, 0.95 prediction power. Hold that thought. Later we'll hit a model
> scoring 0.92 that nothing warned us about, and we only found it by checking
> feature importance ourselves. The tool catches the obvious leak. You have to
> catch the subtle one."*

That makes Demo 2 and Demo 7 bookends instead of two unrelated demos.

### Notes on the flow files

Both were hand-authored against a verified AWS sample
(`aws-samples/amazon-sagemaker-data-wrangler-hospital-readmission-prediction`)
after two failed attempts at guessing the schema. Three rules learned the hard
way, worth knowing before you edit them:

1. `infer_and_cast_type` needs a top-level `trained_parameters.schema` dict of
   column -> type. Omit it and you get
   `TypeError: 'NoneType' object is not subscriptable`.
2. SOURCE nodes need `outputs[].sampling` with `sampling_method` / `limit_rows`.
3. **Nodes must be in dependency order** - every input must appear earlier in
   the `nodes` array, or you get `KeyError: '<node-id>#default'`.

Only operators proven by the sample are used: `s3_source`,
`infer_and_cast_type`, `custom_pandas`, `join_tables`, `manage_columns`
(Drop column variant only), `visualizations.quick_model`.

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

**Slot:** Module 2 · **Baked:** `splits`, `clarify`

### Processing is not another tool — it's the substrate

This is the demo that ties Module 2 together, and you can prove it from the
console with no code at all.

Go to **SageMaker AI → Processing → Processing jobs**. In that one list you will
see:

```
Clarify-Explainability-...        <- Clarify is a Processing job
Clarify-Bias-...                  <- so is the bias half
roi-smdemo-autopilot-t3-1-...     <- so is Autopilot's data step
```

> *"Processing isn't a tool sitting alongside Data Wrangler and Clarify. It's
> what they run ON. Data Wrangler's Export button generates a Processing job.
> Clarify IS a Processing job with a particular container. A preprocessing step
> in a Pipeline is a Processing job. Learn this one and you've learned what
> those others are doing underneath."*

That reframes the whole module: Data Wrangler is the visual front door, Spark is
the big-data front door, and **Processing is the "I just have a script" front
door** — and it's also the engine the other services are built on.

### What the slides list, and why it's one thing

Your Module 2 deck lists Processing for "data processing, feature engineering,
data validation." Those aren't three features — they're three jobs people hand
it. The service itself is one sentence:

> **Here's my script, here's a container, here's S3 in and S3 out, run it on a
> machine this size.**

### "Here's how you make it"

Open `shared/prepare_ml_data.py`. Point out that there is **not one SageMaker
import in the data logic** — it's plain pandas.

> *"That's the whole point. Processing doesn't ask you to learn a framework. Any
> script that reads a path and writes a path will run."*

### "Here's one I made earlier"

S3 → `ml/gas/train/` · `validation/` · `test/`

Real, verified numbers to put on screen:

| split | rows | positive rate |
|---|---|---|
train | 104,956 | 0.2505 |
validation | 22,796 | 0.2346 |
test | 22,248 | 0.2541 |

19 columns, `high_demand` first.

### Spend 60 seconds on the honest bit

**Group leakage.** CEC consumption is *monthly*, so every daily row inside a
county-month carries the same label.

> *"Split those rows at random and the same county-month lands on both sides.
> The model sees its test labels during training and the score is inflated for
> free. So we split by county-month group — 5,530 groups, assigned whole."*

**47% of rows have no precipitation reading.** Many GHCN stations measure
temperature but not rain.

> *"A null means 'no gauge', not 'no rain'. So we impute zero AND add a
> precip_reported flag — otherwise the model can't tell a dry day from a missing
> instrument. And we do it before sampling, not after, or asking for 150,000
> rows quietly hands you 79,000."*

### The cost warning worth passing on

While you're in the Processing jobs list, point at the Clarify job:

> *"Clarify stands up a shadow endpoint to get predictions for SHAP. That
> endpoint bills while the job runs — and if the job fails, it can be left
> behind. Processing jobs can have children. Know what yours start."*

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

## Demo 6a — Built-in algorithm: Random Cut Forest (5 min)

**Slot:** Module 3 Model Development, slide 13 — the deck's own *optional*
built-in-algorithm demo slot. Day 2.
**Baked:** ✅ `roi-smdemo-gas-rcf-261027-0750`, 164 billable seconds.

**The framing:** every other demo is supervised and uses the `high_demand`
label we invented. This one deletes that column. Unsupervised anomaly
detection — "which rows don't look like the others" — because the expensive
surprises in a utility are the ones nobody labelled in advance.

**Here's how you make it:** `04-training/builtin-rcf/launch_rcf.py`. No
training script at all: a built-in is an AWS-maintained container you address
by name, so you bring data and hyperparameters and nothing else.

**Here's one I made earlier:** the Completed job, its image URI, and
`feature_dim=18`.

🔴 Stop after training — the slide says so, and scoring would mean an
hourly-billed endpoint.

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

## Demo 9 — Autopilot / Canvas (5 min)

**Slot:** Module 3 Model Development, slide 40 — the deck has its own Autopilot demo slot. Day 2.
**Baked:** ✅ `roi-smdemo-gas-autopilot`, run 2026-10-26. Best candidate
`WeightedEnsemble-L3-FULL`, accuracy **0.8800**, 10 candidates, target
`high_demand`.

> 🔴 **Do not re-run it live. One run is $9.26.** Autopilot picks its own
> instance type for each trial — it chose `ml.r5.16xlarge` (~$4.84/hr) and ran
> 10 of them in parallel. `max_candidates` caps the trial *count*, not the
> instance size, and there is no parameter that does. This is the single most
> expensive thing in the repo; the completed job is the demo.

**The framing that lands:** Autopilot is the *engine*; there are three front
doors — SDK (code), Studio UI (low-code), Canvas (no-code). Same ranked
leaderboard out of all three.

**Here's one I made earlier:** the candidate leaderboard.

⚠️ Canvas session — kill it afterwards.

---

## Demo 10 — Clarify: bias and explainability (5 min)

**Slot:** Module 3 Model Development, Lab 6 (slide 48). Day 2.
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

## Demo 11 — Deployment and inference (5 min)

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

## Readiness

Check before you commit to a demo in a running class.

| # | Demo | Code | Artifact baked | Safe to demo |
|---|---|---|---|---|
| 1 | Studio tour | n/a | n/a | ✅ |
| 2 | Data Wrangler | ⚠️ flow is a stub | ✅ data | ⚠️ live-build only |
| 3 | PySpark, serverless (Glue) | ✅ verified | ✅ notebook + Glue run | ✅ |
| 4 | SageMaker Processing | ⚠️ partial | ✅ splits | ⚠️ talk-through |
| 5 | Feature Store | ✅ verified | ✅ `roi-smdemo-gas-features` | ✅ |
| 6a | Built-in algo (RCF) | ✅ verified | ✅ `roi-smdemo-gas-rcf-261027-0750` | ✅ |
| 6 | Training | ✅ verified | ✅ | ✅ |
| 7 | Experiments + metric arc | ✅ verified | ✅ baseline + 4 HPO trials | ✅ |
| 8 | HPO | ✅ verified | ✅ `roi-smdemo-gas-hpo-261026-1514` | ✅ |
| 9 | Autopilot | ✅ verified | ✅ `roi-smdemo-gas-autopilot` | ✅ from artifact — never re-run live ($9.26) |
| 10 | Clarify | ✅ ported | see `--status` | check |
| 11 | Deployment | ✅ ported | live | ⚠️ run once first |

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
4. **Run Demo 11 once offline** before trusting it live.
5. **Leave Autopilot out of the prebake list deliberately** — `--all` must
   never trigger a $9.26 job. Launch it by hand when the artifact is missing.
