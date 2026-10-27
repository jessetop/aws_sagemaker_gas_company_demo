# Day 2 runbook — click by click

Day 2 of MLASMS is **Module 4 (Deployment & Inference)** and **Module 5
(Monitoring)**, then the two "Together" sessions. So the demos shift from *how
do I prepare data* to *how does a model get served and watched*.

Same shape as Day 1: where to click, what you're looking at, what to say.

---

## 0. Before you start

```bash
python shared/verify_demos.py        # must print ALL VERIFIED
```

Then one thing that is **Day 2 specific** and must be started in the morning,
because it needs a live endpoint:

```bash
python 07-deployment/monitor_demo_endpoint.py
```

> 🔴 **That endpoint bills (~$0.12/hr on ml.m5.large) until you delete it.** It
> has to stay alive because Model Monitor compares captured live traffic against
> a baseline, and data capture only works on real-time, instance-backed
> endpoints — serverless cannot capture. Over a teaching day that's about $1.
> Forget it for a week and it's $20.
>
> **The Canvas reaper does NOT catch endpoints.** Teardown is manual:
> ```bash
> python 07-deployment/monitor_demo_endpoint.py --delete
> ```

| | |
|---|---|
**Studio** | https://d-nvvqokjr2qep.studio.us-east-1.sagemaker.aws |
**Bucket** | `roi-smdemo-029331796573-us-east-1` |
**Region** | us-east-1 — check the selector says N. Virginia |

---

## Recap the spine in 30 seconds

> *"Yesterday we took two hundred million weather observations down to 1.67
> million California station-days joined to county gas consumption, and we built
> a model that predicts high-demand months. Today: how does that model actually
> get served, and how do you know when it stops working?"*

---

## Demo 6 — Training jobs (5 min)
**Module 4 lead-in** · **Baked:** ✅ verified

### Where to go
**SageMaker AI console → Training → Training jobs** →
`roi-smdemo-gas-train-2026-10-26-16-04-58-308`

### What you're looking at
| Field | Value |
|---|---|
validation:auc | **0.9235** |
validation:accuracy | **0.8794** |
Billable time | **145 seconds** |
Instance | ml.m5.large |
Artifact | `s3://sagemaker-us-east-1-.../output/model.tar.gz` |

### "Here's how you make it"
Open `04-training/launch_training.py` — the Estimator: entry point, instance
type, hyperparameters. Then `04-training/train.py` and the SageMaker contract:

> *"Three env vars and a print statement. `SM_CHANNEL_TRAIN` is where the data
> shows up, `SM_MODEL_DIR` is where you leave the model, and metrics are just
> `name=value` printed to stdout — SageMaker scrapes them with a regex. That's
> the whole contract. No framework to learn."*

Point at **145 billable seconds**:

> *"Two and a half minutes of compute. You pay for that, not for a cluster
> sitting idle."*

---

## Demo 7 — Experiments, and the honest metric (5 min)
**Module 4** · **Baked:** ✅ 5 runs logged
**This is your strongest demo of the two days. Don't cut it.**

### Where to go
**SageMaker AI console → Experiments** → `roi-smdemo-gas-experiment`

Five runs are already there with real parameters and metrics:

| Run | validation:auc |
|---|---|
`train-2026-10-26-16-04-58-308` (baseline) | 0.9235 |
`hpo-261026-1514-001-4138bb7d` | **0.9365** ← best |
`hpo-261026-1514-002-1ff0ac97` | 0.9332 |
`hpo-261026-1514-003-4d1c025f` | 0.9244 |
`hpo-261026-1514-004-0e9c76ce` | 0.9204 |

Select them all → **Compare**. Point at how little the objective moves:

> *"Four tuning trials and the AUC moves by one and a half points. Hold that
> thought — it matters in a minute."*

### Then run the arc. Three minutes, and it's the whole value of the session.

| | AUC |
|---|---|
all features | **0.9235** |
calendar only (`obs_month`, `season_*`, `is_heating_season`) | 0.9043 |
weather only | 0.8298 |
**deseasonalised label** | **0.5159** |

Feature importance on the baseline: `season_Winter` **0.705**, `obs_month`
**0.216**. Everything else shares 0.079.

> *"We got 0.92 and we were pleased. Then we looked at feature importance:
> seventy percent of the model was one column — is it winter. So we asked the
> harder question: was* this *January unusual for this county's Januaries? And
> the model fell to 0.52. A coin flip.*
>
> *The model wasn't bad. The question was easy, and we didn't notice until we
> checked. And remember those four tuning trials that barely moved the needle?
> That's why. The signal was in the label definition, not the hyperparameters.
> Tuning is the last thing you reach for, not the first."*

Then the diagnosis:

> *"The label is a county-MONTH aggregate. The features are a single
> station-DAY. One day's weather can't tell you whether a whole month was
> unusual. The grain doesn't match — and no amount of tuning fixes a question
> asked at the wrong resolution."*

### Tie it back to Day 1
> *"Yesterday Data Wrangler caught a leak for us automatically — one column with
> 0.95 prediction power, flagged in red. Nothing flagged this one. The tool
> catches the blatant leak; you have to catch the subtle one."*

### Reproduce it live if you have time
```bash
python shared/prepare_ml_data.py --no-calendar      # 0.92 -> 0.83
python shared/prepare_ml_data.py --deseasonalize    # -> 0.52
```

---

## Demo 8 — Hyperparameter tuning (5 min)
**Module 4** · **Baked:** ✅ `roi-smdemo-gas-hpo-261026-1514`

### Where to go
**Training → Hyperparameter tuning jobs** → `roi-smdemo-gas-hpo-261026-1514`

### What you're looking at
4 of 4 trials completed, 0 failed. Best trial:

```
roi-smdemo-gas-hpo-261026-1514-001-4138bb7d
  validation:auc  = 0.9365
  learning-rate   = 0.2098380788914352
  max-depth       = 6
```

### "Here's how you make it"
`05-experiments-tuning/launch_tuning.py` — the search space, objective
`validation:auc`, max jobs, max parallel.

> *"Max parallel is a cost dial, not a speed dial. Four jobs two at a time costs
> the same as four jobs one at a time — it just finishes sooner. What costs you
> is max_jobs."*

### The honest read
> *"Baseline 0.9235, best trial 0.9365. One and a third points for four training
> jobs. On this problem the hyperparameters barely matter — which you only know
> because you ran the sweep and looked."*

---

## Demo 10 — Deployment and inference (5 min)
**Module 4, the main event** · **Runs LIVE** — ✅ verified end to end

The exception to the cooking show: this one is fast enough to run for real, and
watching the endpoint get deleted is the point.

```bash
python 07-deployment/deploy_and_infer.py
```

### What you'll see (verified output)
```
using artifact from roi-smdemo-gas-train-2026-10-26-16-04-58-308
-----!endpoint InService: roi-smdemo-gas-endpoint
  P(high_demand) = 0.0560
  P(high_demand) = 0.9170
  P(high_demand) = 0.6379
deleted endpoint: roi-smdemo-gas-endpoint
```

### What to say
The `-----!` is the deploy progress. Then three real predictions on held-out
station-days:

> *"Six percent, ninety-two percent, sixty-four percent. Three different days,
> three different confidences that the county was in a high-demand month."*

Then the last line:

> *"Notice what the script does last. It deletes the endpoint. An endpoint bills
> by the hour from the moment it reaches InService, whether or not anybody calls
> it. If you take one operational habit from this course: the teardown goes in
> the same script as the setup, not in a runbook you'll forget."*

---

## Demo 12 — Model Monitor + Model Card (5 min)
**Module 5, Monitoring** · ✅ **verified**

### Two ways to give this. Pick before class.

| | Endpoint? | Cost | You can show |
|---|---|---|---|
**A. Artifacts only** (recommended) | none | **$0** | captured records, Model Card |
**B. Live endpoint** | yes, all day | ~$1/day | the above + an InService endpoint |

**Option A works because the captured records and the Model Card already exist
and outlive the endpoint.** They are sitting in S3 right now from a verified
run. You lose only the ability to point at a live endpoint in the console --
everything you actually *talk about* is still there.

If you want Option B, start it in the morning:

```bash
python 07-deployment/monitor_demo_endpoint.py
```

> 🔴 **It bills ~$0.13/hr until deleted, and the Canvas reaper does NOT catch
> endpoints.** Teardown is manual:
> ```bash
> python 07-deployment/monitor_demo_endpoint.py --delete
> ```

### Where to go
**S3 →** `ml/gas/datacapture/roi-smdemo-gas-monitor/AllTraffic/2026/10/26/23/`
→ open any `.jsonl`

(Option B only: first show **Inference → Endpoints → `roi-smdemo-gas-monitor`
→ Data capture**, so they see where the path comes from.)

### What you're looking at — a real captured record
```
input  : 240.5,0.0,0.0,1.0,9.0,0.0,31.1,68.99,10.0,21.1,1.0,...
  type : text/csv
output : 0.05597794607887812
time   : 2026-10-26T23:49:33Z
```

Three JSONL files, ~50 KB, one line per inference — the input row, the
prediction, and a timestamp, written for **every** request because capture is
set to 100%.

> *"Six percent. That's what the model said about that station-day, and it's
> written down forever with the exact inputs that produced it. That's the
> foundation of monitoring: you cannot detect drift you never recorded."*

> *"Model Monitor doesn't watch your model. It watches your DATA. It builds a
> statistical baseline from your training set, then compares what's actually
> arriving at the endpoint against it. When live traffic drifts away from the
> baseline, that's the alarm — and it fires long before anyone notices the
> predictions got worse."*

**Make it concrete for a utility:**

> *"Our model learned from 2015-2024 California weather. Climate shifts, new
> stations come online, old ones go offline. In three years the distribution
> arriving at this endpoint won't be the distribution it trained on. Nobody
> will tell you. This is how you find out."*

### Why real-time and not serverless
Worth 20 seconds because people ask:

> *"Data capture only works on real-time, instance-backed endpoints. Serverless
> can't capture — there's no persistent instance to write from. So if monitoring
> is a requirement, that decides your endpoint type before cost does."*

### Then the Model Card
**Inference → Model cards** → `roi-smdemo-gas-demand-classifier`

Populated from the real training metrics.

> *"A model card is the governance artifact — intended use, risk rating,
> training metrics, caveats. For a regulated utility this is the thing that
> makes a model auditable. And notice the risk section says the model is
> sensitive to heating degree days and station elevation. That's not boilerplate,
> that's what we actually learned yesterday."*

### 🔴 Tear it down when you finish Module 5
```bash
python 07-deployment/monitor_demo_endpoint.py --delete
```
Say it out loud as you do it. It reinforces Demo 10's lesson.

---

## Demo 11 — Autopilot (5 min)
**Wherever AutoML fits** · ✅ **verified**

### Where to go
**SageMaker AI console → Training → AutoML jobs** → `roi-smdemo-gas-autopilot`
→ the candidate leaderboard.

### What you're looking at (verified)

10 candidates, ENSEMBLING mode, target `high_demand`, 15,000 rows.

| Rank | Candidate | Accuracy |
|---|---|---|
1 | `WeightedEnsemble-L3-FULL` | **0.8800** |
2-8 | `WeightedEnsemble-L2-FULL` (×7) | 0.8687 |
9 | `WeightedEnsemble-L2-FULL` | 0.8664 |
10 | `WeightedEnsemble-L2-FULL` | 0.8594 |

### The framing
> *"Autopilot is the engine. Three front doors to it: the SDK if you write code,
> the Studio UI for low-code, Canvas for no-code. All three produce this same
> leaderboard. So 'should we use Autopilot or Canvas' is a malformed question —
> Canvas IS Autopilot with a different front door."*

### The comparison that lands

Put these two numbers next to each other:

| | Accuracy |
|---|---|
Autopilot — 10 candidates, 3-layer weighted ensemble | **0.8800** |
Our hand-built GradientBoosting — one model, 145 seconds | **0.8794** |

> *"Six ten-thousandths of a point. Autopilot searched ten candidates and
> stacked a three-layer ensemble to match a single scikit-learn model we wrote
> in an afternoon. Look at the spread too — 0.859 to 0.880 across all ten.
> Everything works about equally well on this problem."*

That echoes the HPO finding from Demo 8 and sets up the real point:

> *"And here's the thing. Autopilot inherited our label definition. So it is
> confidently and very efficiently solving the same slightly-wrong problem we
> were — the one we found in Demo 7, where seventy percent of the model was 'is
> it winter'. AutoML optimises the model. It cannot tell you that you asked the
> wrong question. That is still your job, and it is the only part of this that
> isn't automatable."*

Strongest closing line available for an AutoML segment, and it only works
because they watched you find the wrong question earlier.

⚠️ If you demo this through Canvas rather than the console, that's a billable
session — `powershell -File cleanup/kill_canvas.ps1` after. Note that opening
Canvas also auto-creates an EMR Serverless app
(`sm-canvas-data-wrangler-emr-app-<profile>`); it doesn't bill at rest, and
`cleanup.ps1` removes it.

## Day 2 running order

| Slot | Demo | Min | Notes |
|---|---|---|---|
Module 4 open | 6 — Training jobs | 5 | |
Module 4 | 7 — Experiments + metric arc | 5 | **the keeper** |
Module 4 | 8 — HPO | 5 | |
Module 4 | 10 — Deploy + infer | 5 | runs live |
Module 5 | 12 — Monitor + Model Card | 5 | needs morning endpoint |
flexible | 11 — Autopilot | 5 | |

~30 minutes across the day.

**If you're short:** cut 8 (HPO) — its best line is already inside Demo 7. Never
cut 7.

---

## End of Day 2

```bash
python 07-deployment/monitor_demo_endpoint.py --delete   # the billing one
powershell -File cleanup/kill_canvas.ps1                 # if you opened Canvas
python cleanup/verify_teardown.py                        # must print CLEAN
```

If `verify_teardown.py` reports anything, it tells you the command to fix it.

---

## Break glass

| Symptom | Fix |
|---|---|
Empty console panel | **Check the region** — N. Virginia |
`--model-data` error | Shouldn't happen now; both deploy scripts resolve it themselves |
Endpoint stuck Creating | Give it 8 min; talk over it or move to Demo 11 |
Monitor endpoint missing | You skipped the morning step — run `monitor_demo_endpoint.py` |
Experiments panel empty | `python shared/populate_studio_classic.py` |
Any permissions error | `python 00-setup/preflight.py` names the fix |

**Fallback:** `TEST_LOG.md` has every verified number. If something dies on
stage, switch to it and say so — nobody minds a recorded result, they mind being
misled about one.
