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

**Here's how you make it:** the notebook
`04-training/builtin-rcf/rcf_builtin.ipynb`, run in Studio JupyterLab — this is
a notebook demo, which is what the slide actually asks for. No training script
at all: a built-in is an AWS-maintained container you address by name, so you
bring data and hyperparameters and nothing else.
(`launch_rcf.py` is the same thing headless, for baking it ahead of time.)

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

## Demo 7a — Debugger: looking inside the training job (5 min)

**Slot:** Module 3, straight after Demo 7. **No deck slide asks for this one** —
it is an extra, and the first thing to cut if Module 3 runs long.
**Baked:** ✅ `roi-smdemo-gas-debugger-2026-10-28-04-34-32-149`, 768 billable
seconds, both rules `NoIssuesFound`.

### The framing

Every other demo today showed you a training job's **inputs and outputs** — data
in, metrics out, 145 billable seconds. The job itself was a black box that
happened for three minutes and then was over.

> *"You get one number at the end. Did the loss actually go down, or did it flatten
> at round four and burn the other fifty-six? Did it start memorising the training
> set halfway through? You cannot tell from an AUC. Debugger is how you watch the
> training process instead of just its receipt."*

### Here's how you make it

`06-clarify-debugger-groundtruth/launch_debugger_xgboost.py`. Show the
`DebuggerHookConfig` — three collections, `save_interval: 1` — and the two
`Rule.sagemaker(...)` lines. That is the entire instrumentation.

**Say the constraint out loud, because it is the thing people get wrong:**

> *"This demo trains the same task on the same data as Demo 6, but with built-in
> XGBoost instead of our scikit-learn script. Not because XGBoost is better —
> because Debugger only hooks XGBoost, PyTorch, TensorFlow and MXNet. Our
> `train.py` cannot emit a single tensor no matter what we configure. If you want
> this visibility, it constrains your framework choice, and that is worth knowing
> before you pick one."*

🟡 **Hit cancel:** ~13 minutes. Nobody watches that.

### Here's one I made earlier — verified

**SageMaker AI → Training → Training jobs →**
`roi-smdemo-gas-debugger-2026-10-28-04-34-32-149` → **Debugger** tab.

| | |
|---|---|
Algorithm | built-in XGBoost `1.7-1`, **no training script** |
Input | `pipeline/train/` — 104,956 rows × 11 features, headerless, label-first |
Rounds | 60, tensors saved **every** round |
Instance | ml.m5.large, **768 billable seconds** |
Tensors | **123 objects** in `s3://<bucket>/debugger/xgboost/` |

| metric | train | validation |
|---|---|---|
logloss | 0.2514 | **0.2741** |
auc | 0.9469 | **0.9315** |

**The loss curve is the picture.** Both curves descend and the gap between them
stays small — that is what "not overfitting" looks like, rather than something
you take on faith.

### The rules, and why a boring result is the result

| Rule | Outcome |
|---|---|
`LossNotDecreasing` | **NoIssuesFound** |
`Overfit` | **NoIssuesFound** |

> *"Both rules came back with nothing. That is the answer — not a failed demo.
> The point is that something was watching for the two most common ways training
> goes wrong, it was watching every round, and I did not write either check. A
> rule that finds nothing is a rule that told you it is safe to stop looking."*

If someone asks what a hit looks like: `LossNotDecreasing` fires when the loss
flattens for a configured number of steps, and `Overfit` fires when validation
loss rises while training loss keeps falling. Here, `0.2514` vs `0.2741` — a
0.023 gap after 60 rounds — is well inside tolerance.

### Two callbacks that make this demo earn its slot

**Back to Demo 4 — rules are Processing jobs.** Go to **Processing → Processing
jobs** and find them:

```
roi-smdemo-gas-debugger-20-LossNotDecreasing-ee820a8f
roi-smdemo-gas-debugger-20-Overfit-5862312c
```

> *"There they are, in the same list as Clarify and Autopilot's data step. I told
> you this morning that Processing is the substrate. A Debugger rule is a
> Processing job with a rule container. Learn Processing once and you keep
> recognising it all day."*

**Back to Demo 7 — the job could have told us.** The hook captured
`feature_importance` and `average_shap` collections alongside the loss, for no
extra code.

> *"Remember the arc from twenty minutes ago — we found that seventy percent of
> the model was 'is it winter', and we found it by going and looking afterwards.
> This training job captured feature importance and SHAP values while it trained,
> automatically, because we listed two collection names. The finding that took us
> a day was available at round one."*

That is the most useful thing in this demo: not a feature tour, but *you already
had this and did not look.*

### The fourth 0.93 — worth 20 seconds

| Path | Algorithm | Features | validation AUC |
|---|---|---|---|
Demo 6 — standalone training | sklearn GBM | 18 | 0.9235 |
Demo 12 — Pipeline | sklearn GBM | 11 | 0.9261 |
**Demo 7a — Debugger** | **built-in XGBoost** | **11** | **0.9315** |
Demo 8 — HPO best trial | sklearn GBM | 18 | 0.9365 |

> *"Four code paths, two different algorithms, two different feature sets, and
> every one of them lands between 0.92 and 0.94. The model is not the variable
> here. The question is — and we already know the question was too easy."*

### 🔴 The cost warning, and a correction worth passing on

The script's own comment said these rules run **"in parallel, for free."** That is
wrong, and the measured numbers say so:

| | Instance | Duration | |
|---|---|---|---|
Training job | ml.m5.large | 768 s | ~$0.025 |
`LossNotDecreasing` | ml.t3.medium | 773 s | ~$0.011 |
`Overfit` | ml.t3.medium | 773 s | ~$0.011 |

> *"Each rule is its own instance, and it bills for the whole length of your
> training job, not for the moment it finds something. Two rules here cost about
> as much as the training did. At this scale that is five cents and who cares —
> on a six-hour job on big instances, attaching eight rules is a real line item.
> Rules are cheap. They are not free, and the docs will tell you they are."*

Comment now corrected in the script.

### Rebuild it

```bash
python 06-clarify-debugger-groundtruth/launch_debugger_xgboost.py          # ~13 min, ~$0.05
python 06-clarify-debugger-groundtruth/launch_debugger_xgboost.py --wait   # + stream rule outcomes
```

⚠️ **It reads `pipeline/train/`, so the Pipeline must have run first.**
`ml/gas/train/` will not work — it has a header row and built-in XGBoost cannot
parse one. On a fresh account: `python 08-pipelines/build_pipeline.py --start`.

---

## Demo 7b — MLflow: the same arc, a second tracker (5 min)

**Slot:** Module 3. Either straight after Demo 7, or **instead of** Demo 7's
console walkthrough if you would rather give it from a notebook.
**Baked:** ✅ MLflow experiment `gas-demand-the-honest-metric`, 4 runs.
**Notebook:** [`05-experiments-tuning/experiments_and_mlflow.ipynb`](05-experiments-tuning/experiments_and_mlflow.ipynb)
**Cost:** **$0.** Nothing hourly is created.

### Why this exists

Somebody always asks "can we just use MLflow?" This answers it with their own
data instead of an opinion — and the answer turns out to be more interesting
than yes or no, because **SageMaker has two different MLflow resources and only
one of them is free.**

### 🔴 The cost fact that is worth the whole demo

| Resource | ARN | Billing |
|---|---|---|
**MLflow App** | `mlflow-app/...` | serverless, no Start/Stop, **$0 at rest** |
**MLflow Tracking Server** | `mlflow-tracking-server/...` | **$0.60/hr** Small, from Created until Deleted |

Both are addressed by ARN as the MLflow tracking URI. **The ARN is the only
thing that tells them apart.** A Small tracking server left running is
$14.40/day, ~$432/month, with no idle shutdown.

> *"This account has had an MLflow App sitting in it since July. It was attached
> to a Studio domain that got deleted, it outlived that domain by nearly four
> months, and nobody noticed — because it costs nothing. If that had been a
> tracking server instead, the same four months of not noticing would have been
> about seventeen hundred dollars. Same product name. Different resource."*

Verified from Cost Explorer: **August and September 2026 were $0.00** for all of
SageMaker while that app existed the whole time.

### What the notebook shows

Four parts, ~20 cells. It is the only artifact in the repo that puts
**SageMaker Experiments and MLflow side by side on the same question.**

**Part 1 — SageMaker Experiments.** Pulls the five baked runs via the SDK:

| run | learning_rate | max_depth | validation_auc |
|---|---|---|---|
hpo-...-001 | 0.2098 | 6 | **0.9365** |
hpo-...-002 | 0.2886 | 4 | 0.9332 |
hpo-...-003 | 0.0139 | 6 | 0.9244 |
train-2026-10-26 (baseline) | 0.1 | 3 | 0.9235 |
hpo-...-004 | 0.1679 | 2 | 0.9204 |

`validation_accuracy` is `NaN` on the HPO rows **and that is correct** — a tuning
job logs only the objective it was told to optimise. Say so before anyone asks.

**Part 2 — MLflow: the arc.** The Demo 7 story, as four comparable runs:

| run | features | label | validation AUC |
|---|---|---|---|
all-features | 18 | within county | **0.9235** |
calendar-only | 6 | within county | 0.9044 |
weather-only | 12 | within county | 0.8297 |
**deseasonalised-label** | 18 | within county **AND month-of-year** | **0.5159** |

Then feature importance, logged alongside the metrics so it is inspectable in
the UI rather than asserted on a slide:

```
season_Winter   0.705
obs_month       0.216
elevation_m     0.047
```

> *"Same features in the top row and the bottom row. The only thing that changed
> is what we asked. Ninety-two points to fifty-two."*

**Part 3 — log a run live.** 15,000 rows, 40 trees, finishes while you talk.
Three lines — `log_params`, `log_metric`, `set_tag` — and it appears next to the
others. That is the entire MLflow API that matters.

**Part 4 — which one.** The honest comparison:

| | SageMaker Experiments | Managed MLflow |
|---|---|---|
Cost | free | App free · Server $0.60/hr |
Logging | automatic from training jobs | you call `log_metric` |
Works off SageMaker | no | yes — it is real MLflow |
Portable off AWS | no | yes |

> *"If everything you train is a SageMaker training job, Experiments gives you
> this for free and you write no code. If your team already lives in MLflow, or
> trains anywhere else, use MLflow. And neither one would have caught the problem
> in part two — a tracker records what you measured. It cannot tell you the
> question was too easy."*

### Running it

**Studio → JupyterLab →**
`aws_sagemaker_gas_company_demo/05-experiments-tuning/experiments_and_mlflow.ipynb`

⚠️ **Cell 1 is `%pip install -q mlflow sagemaker-mlflow`** — neither is in the
stock Studio image, and `sagemaker-mlflow` is the plugin that lets MLflow
authenticate with your IAM role. Without it, setting an ARN as the tracking URI
fails. Run that cell before class and restart the kernel if it asks.

### Rebuild the runs

```bash
python 05-experiments-tuning/mlflow_log_ablation.py        # ~6 min local, $0
```

Two traps already handled in that script, both of which cost time:

1. **A shuffled-label control does not work on this dataset** and was removed.
   Measured across seeds it returned AUC 0.3225 / 0.5073 / 0.3404 instead of
   centring on 0.50 — because the label is a county-month aggregate, so the
   effective sample is ~5,530 groups, not 150,000 rows. The deseasonalised run is
   the control that behaves.
2. **The deseasonalised splits are written to `ml/gas-deseason/`, never
   `ml/gas/`.** Regenerating `ml/gas/` would overwrite the baked splits that
   every other Day 2 demo depends on.

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

## Demo 12 — Pipelines and lineage: where did this model come from? (5 min)

**Slot:** Day 2, Module 4 — pairs with **Lab 9: Pipelines + Model Registry**
(Mod04 slide 23). Give it *before* the lab; the lab then builds what they just
watched.
**Baked:** ✅ `roi-smdemo-gas-pipeline`, execution **`p9khxwja52g2`**, run
2026-10-27. All 10 steps Succeeded.

**A student asked for this one.** It exists because somebody in the room wanted
to see lineage, which is the best possible reason for a demo to exist — say so
out loud.

### The question this demo answers

> *"Somebody hands you a model and asks what it was trained on. Not 'which
> algorithm' — what **data**, which version, who approved it, and is it still
> the one in production. If the answer is 'let me check my notebook', you don't
> have an answer."*

### Here's how you make it — the DAG

Open `08-pipelines/build_pipeline.py` and show the ten steps. Don't read the
code; read the **shape**:

```
PreprocessGasData        Processing     ml.m5.2xlarge
DataBiasCheck            ClarifyCheck   ml.m5.large
TrainGasModel            Training       ml.m5.large
EvaluateModel            Processing     ml.m5.large   -> evaluation.json
CheckAUC                 Condition      AUC >= 0.55
   if passed:
     CreateGasModel-RepackModel     Training
     CreateGasModel-CreateModel     Model
     ModelBiasCheck                 ClarifyCheck   + shadow endpoint
     ModelExplainabilityCheck       ClarifyCheck   + shadow endpoint
     RegisterGasModel               RegisterModel  -> version 2
```

**The step to point at is `CheckAUC`.** It's the only one that isn't compute:

> *"That's a gate. If the model doesn't clear the bar, the register branch never
> runs and nothing lands in the registry. The DAG refuses to promote a bad
> model, and it refuses without a human in the loop. That's the difference
> between a script that trains a model and a pipeline that governs one."*

**Hit cancel:** the full run is ~36 minutes. Nobody watches that.

### Here's one I made earlier — verified numbers

Studio → **Pipelines → `roi-smdemo-gas-pipeline` → execution `p9khxwja52g2`**.
The visual DAG renders with the condition branch drawn in, which is the picture
worth more than the code.

| Step | Wall clock | Result |
|---|---|---|
PreprocessGasData | 2m33s | train 6.0 MiB / validation 1.3 MiB / test 1.3 MiB |
DataBiasCheck | 5m03s | pre-training baseline on `is_heating_season` |
TrainGasModel | 3m18s | `pipelines-p9khxwja52g2-TrainGasModel-IGJ6PCZl4b` |
EvaluateModel | 5m04s | **AUC 0.9261**, accuracy 0.8773 |
CheckAUC | 0m00s | 0.9261 ≥ 0.55 → **passed** |
RepackModel | 2m48s | |
CreateGasModel | 0m01s | |
ModelBiasCheck | 10m04s | post-training bias |
ModelExplainabilityCheck | 17m35s | SHAP attributions |
RegisterGasModel | 0m01s | **`roi-smdemo-gas-models` version 2, Approved** |

**Worth 20 seconds, and it ties back to Demo 7:** this run scored **0.9261**.
The standalone training job in Demo 6 scored **0.9235** — through a completely
different code path (`08-pipelines/preprocess.py` instead of
`shared/prepare_ml_data.py`).

> *"Same answer twice, two different scripts. So the 0.92 is real — and the
> story from this morning still holds: it's real and it's still the easy
> question. Reproducibility doesn't make a metric honest. It just makes it
> reproducible."*

### The money shot — two versions, side by side

Studio → **Model registry → `roi-smdemo-gas-models`**. There are two versions,
both Approved, near-identical AUC. Open the **Lineage** tab on each.

**Version 1** — you registered it by hand (`register_model_with_reports.py`).
Its graph starts at a training job:

```
ml/gas/{train,validation}/ + sklearn:1.2-1
  -> roi-smdemo-gas-train-2026-10-26-16-04-58-308
  -> model.tar.gz
  -> roi-smdemo-gas-models/1  (Approval + ModelLifeCycle actions)
  -> 4 ModelDeployment actions
```

**Version 2** — the pipeline produced it. Its graph goes back a step further,
to the data it was built from:

```
processed/visual-etl/
  -> pipelines-p9khxwja52g2-PreprocessGasData-8TwHXhhTZ1
  -> pipeline/{train,validation,test}
  -> pipelines-p9khxwja52g2-TrainGasModel-IGJ6PCZl4b
  -> model.tar.gz
  -> roi-smdemo-gas-models/2  + bias & SHAP baselines + the gate that let it in
```

> *"Same model, essentially. One of them can tell you where it came from."*

That contrast *is* the demo. Don't explain lineage as a feature — show two
graphs and let the room notice that one is shorter.

### The bit that gets the "huh" — lineage outlives the resource

All four endpoints in version 1's graph are **deleted**. `list-endpoints` on
this account returns nothing. The graph still has them.

> *"Those endpoints don't exist. The account still knows they existed, what was
> deployed to them, and which model version it came from. That's not a log you
> have to remember to write — SageMaker records it whether you ask or not.
> Deleting the endpoint doesn't delete the fact that you deployed it."*

For a regulated utility that is the whole pitch, and it lands better as a
surprise than as a bullet point.

### Cost — and a correction worth passing on

`08-pipelines/README.md` said "a few dollars per full execution." By
instance-second arithmetic on the durations above, the real figure is **about
$0.16** — the biggest line item is SHAP at ~3½ cents of Clarify plus ~3½ cents
of shadow endpoint.

🟢 **Both shadow endpoints tore themselves down.** Verified: `list-endpoints` is
empty after the run. Worth saying, because Demo 10 warns that a *failed* Clarify
job can orphan one — a succeeded one cleans up after itself.

### Re-running it

```bash
python 08-pipelines/build_pipeline.py            # upsert only, free, no compute
python 08-pipelines/build_pipeline.py --start    # ~36 min, ~$0.16
```

Delete the model `roi-smdemo-gas-pipeline-model` first (the cleanup script
does), or `CreateGasModel` fails on the name collision.

**Two Windows/SDK traps already fixed in the script** — both cost a debugging
session, so don't "simplify" them away:

1. The SDK writes `_repack_script_launcher.sh` in text mode, so on Windows every
   `\n` becomes `\r\n` and the Linux repack container dies with `#015: not
   found`. `_patch_repack_launcher_lf()` rewrites it with `newline="\n"`.
2. `ModelStep` ignores the `name=` you give the model and generates its own at
   run time. The Clarify steps must reference
   `step_create_model.properties.ModelName`, not the literal — a literal fails
   with *"Could not find model ..."*.

---

## Demo 13 — AI-DLC: where all of this came from (5 min)

**Slot:** Day 3, Module 6 or Module 7 — the only demo-free stretch in the whole
deck set, and the natural place for "so how do you actually build this stuff."
**Baked:** ✅ `.kiro/specs/sagemaker-studio-demos/requirements.md` (in the repo
since day one) + `ai-dlc/transcript/`.
**Cost:** **$0 of AWS.** Nothing to delete afterwards.

**The framing:** this is the only demo in the set that is not a SageMaker
service. For three days the room has run notebooks, a Processing job, an HPO
sweep, a pipeline. Somebody had to write all of it. AWS has a published opinion
about who that somebody is now, and the artifact is in the repo they cloned on
Day 1.

> *"Sprints become bolts — hours, not weeks. Epics become units of work.
> Elaboration happens in a mob, with the AI planning and a human at every gate.
> That is the whole vocabulary."*

**Here's how you make it:** at the repo root, `aidlc config --harness claude`,
then paste the unit of work from `ai-dlc/unit-of-work.md` — the anomaly triage
report that Demo 6a deliberately stopped short of. It produces a plan and then
**stops to ask you questions.** That pause is the demo. If it proposes a
SageMaker endpoint, reject it on stage: the method is worth nothing if the gate
isn't real, and the room needs to watch one close.

🟡 **Hit cancel** after the first gate — *"this runs about twenty minutes and I'm
not making you watch it."*

**Here's one I made earlier:** open
`.kiro/specs/sagemaker-studio-demos/requirements.md`. A glossary, user stories,
and EARS acceptance criteria — `THE Dataset_Loader SHALL download a publicly
available dataset of at least 100,000 samples`, `IF the download fails THEN
retry up to 3 times`. 133 lines, none of them hand-typed.

Then land it:

> *"This file is why this repo has folders 00 through 10. The thing you have
> been running for three days came out of one of these."*

**The line that makes it honest** — and the only part of this demo that can't be
faked. Read the spec's dataset requirement out loud, then point at the actual
data:

> *"It asked for a public dataset of a hundred thousand samples. You spent three
> days on two hundred million weather observations and California county therms.
> A human read that line and said no. The agent rebuilt around the override.
> That is the gate doing its job — and it's why 'AI plans, human decides' is the
> whole method and not a slogan."*

⚠️ **This is the one non-deterministic demo in the repo.** `/aidlc` words its
plan differently every run. Rehearse once and keep `ai-dlc/transcript/` open in
a second tab.

---

## Readiness

Check before you commit to a demo in a running class.

| # | Demo | Code | Artifact baked | Safe to demo |
|---|---|---|---|---|
| 1 | Studio tour | n/a | n/a | ✅ |
| 2 | Data Wrangler | ⚠️ flow is a stub | ✅ data | ⚠️ live-build only |
| 3 | PySpark, serverless (Glue) | ✅ verified | ✅ notebook + Glue run | ✅ |
| 4 | SageMaker Processing | ✅ verified | ✅ `roi-smdemo-gas-prep-2026-10-27-15-34-24-552` | ✅ |
| 5 | Feature Store | ✅ verified | ✅ `roi-smdemo-gas-features` | ✅ |
| 6a | Built-in algo (RCF) | ✅ verified | ✅ `roi-smdemo-gas-rcf-261027-0750` | ✅ |
| 6 | Training | ✅ verified | ✅ | ✅ |
| 7 | Experiments + metric arc | ✅ verified | ✅ baseline + 4 HPO trials | ✅ |
| 7a | Debugger (loss curve + rules) | ✅ verified | ✅ `roi-smdemo-gas-debugger-2026-10-28-04-34-32-149` | ✅ extra — no deck slot, cut first |
| 7b | MLflow + Experiments notebook | ✅ verified | ✅ `gas-demand-the-honest-metric`, 4 runs | ✅ $0 — needs the pip cell |
| 8 | HPO | ✅ verified | ✅ `roi-smdemo-gas-hpo-261026-1514` | ✅ |
| 9 | Autopilot | ✅ verified | ✅ `roi-smdemo-gas-autopilot` | ✅ from artifact — never re-run live ($9.26) |
| 10 | Clarify | ✅ ported | see `--status` | check |
| 11 | Deployment | ✅ ported | live | ⚠️ run once first |
| 12 | Pipelines + lineage | ✅ verified | ✅ `p9khxwja52g2`, 10/10 steps, v2 registered | ✅ |
| 13 | AI-DLC (Day 3) | n/a — a method, not code | ✅ spec + `ai-dlc/transcript/` | ✅ $0, rehearse once |

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
3. ~~Port `08-pipelines/preprocess.py`~~ — **done.**
   `02-processing/launch_processing.py` runs it standalone. Doing so found that
   the script had never actually executed: it asked the parquet reader for
   `precip_reported` (derived, not stored) and for `obs_year`/`obs_month`
   (Hive partition columns that live in directory names, not in the files).
   Both now fixed, which also unblocks the Pipeline step.
4. ~~Run the Pipeline once~~ — **done 2026-10-27.** First execution ever,
   `p9khxwja52g2`, all 10 steps Succeeded, no intervention. That retroactively
   validates the `preprocess.py` fix above through a second code path, and it is
   what Demo 12 shows. The README's "a few dollars" cost estimate was ~20× high;
   corrected to ~$0.16.
5. **Run Demo 11 once offline** before trusting it live.
6. **Leave Autopilot out of the prebake list deliberately** — `--all` must
   never trigger a $9.26 job. Launch it by hand when the artifact is missing.
