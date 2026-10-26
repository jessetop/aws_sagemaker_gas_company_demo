# Demo guide — SoCalGas edition

How to actually run this in front of a room. One story, told in the order the
room will follow it, with the exact commands and what to say over each.

**Read this once end to end before class.** Then keep it open on a second screen.

---

## The one-sentence story

> *A gas utility's load is driven by the weather. We're going to take twenty
> years of raw weather observations from every station on earth, narrow them to
> California, work out how cold each county actually got, and line that up
> against how much gas each county burned — then predict high-demand months
> from the weather alone.*

That is the whole series. Every module is one step of that sentence, done two
ways: the old way (standalone SageMaker AI) and the new way (Unified Studio).

Why it lands with SoCalGas: heating degree days is *their* metric. This is not
a toy dataset dressed up in their logo — it is the actual shape of their demand
forecasting problem, built from public data.

---

## Before class — the 20-minute setup

Run these in order. Nothing here needs babysitting.

```bash
cd AWS_SageMaker_Gas_Dataset

# 1. Is the account wired up? (read-only, 10 seconds)
python 00-setup/preflight.py

# 2. Infra: bucket, Studio domain, Canvas cost guard, budgets  (~3 min)
cd terraform && terraform apply && cd ..

# 3. Stage the open data: GHCN weather + station/county/consumption lookups
#    (~4 min, 419 Parquet objects, 720 MB, all server-side S3 copies)
python 00-setup/stage_dataset.py --start-year 2015 --end-year 2024

# 4. Run the pipeline  (~10 min, ~$0.30)
python 01-data-prep/new-visual-etl/run_glue_job.py --start --workers 4

# 5. Build the ML splits  (~1 min, free, runs locally)
python shared/prepare_ml_data.py
```

Then confirm the cost guard is alive — this is the one check worth never
skipping:

```bash
aws logs tail /aws/lambda/roi-smdemo-gas-canvas-reaper \
  --profile roitraining --region us-east-1 --since 2h
```

You want to see a line per region, e.g.
`[us-east-1] swept 1 domain(s), 0 app(s), 0 of type ['Canvas']`.

### The one thing that will cost you money

**Canvas.** A Canvas session is ~$32–64/day and it keeps billing after you
close the browser tab — you have to delete the *app*, not the tab. In June 2026
one forgotten session was $202 of a $218 bill.

The reaper now kills idle Canvas after 60 minutes, and any Canvas after 10
hours regardless. But when you finish the Canvas segment, do this anyway:

```bash
powershell -File cleanup/kill_canvas.ps1
```

---

## What is demoable right now

Be straight with yourself about this before you plan the session.

| # | Module | State |
|---|---|---|
| — | Infra / cost guard | ✅ deployed and verified |
| 0 | Setup + dataset | ✅ runs, 419 objects staged |
| 1 | Data prep — Visual ETL / Glue | ✅ **run end to end on real data** |
| 2 | Scalable processing — EMR | ⚠️ not ported (still taxi schema) |
| 3 | Feature Store | ⚠️ ported, not yet run |
| 4 | Training | ⚠️ ported, not yet run |
| 5 | Experiments + tuning | ⚠️ ported, not yet run |
| 6 | Clarify / Debugger / Ground Truth | ⚠️ ported, not yet run |
| 7 | Deployment | ⚠️ ported, not yet run |
| 8 | Pipelines | ❌ not ported (`preprocess.py` needs rewriting) |
| 9 | Autopilot / Canvas | ⚠️ ported, not yet run |
| 10 | Custom container | ⚠️ not ported |

"Ported, not yet run" means the code targets the gas schema and imports
cleanly, but has never executed against AWS. **Do not demo an unrun module
live.** Run it once yourself first; that is what turns ⚠️ into ✅.

---

## Module 1 — the headline demo (5 minutes)

This is the one that is proven, and happily it is also the most impressive,
because the numbers are genuinely big.

### What to say

> "Here is every weather observation on earth for the last ten years — two
> hundred million rows. I want California, I want it joined to gas
> consumption, and I want it in a shape a model can learn from."

### What to show

```bash
python 01-data-prep/new-visual-etl/run_glue_job.py --start --workers 4
```

While it runs, walk the canvas: **Unified Studio → Build → Visual ETL**, and
point at the equivalent nodes. The job is a Glue script job, so the *logic* is
in `shared/gas_transforms.py` — show that file; each numbered block `T1`…`T17`
is one node a learner would drag onto the canvas.

### The numbers to put on screen

```
201,486,363 raw worldwide rows  →  1,668,673 California station-days
```

And then the payoff — the aggregate that justifies the whole dataset:

| | mean total_therms | mean hdd65 |
|---|---|---|
| outside heating season | 35.1 M | 3.02 |
| **in** heating season | **49.6 M** | **14.24** |

> "Forty-one percent more gas burned, against four-point-seven times the
> heating degree days. That relationship is the product."

### The three traps worth teaching from this module

These are real bugs that bit during development, which makes them land far
better than invented examples:

1. **`DATE` is a string.** GHCN stores `"20240115"`, not a date. Cast it
   carelessly and Spark's CORRECTED parser returns NULL — silently deleting
   rows rather than erroring. We parse with an explicit format.
2. **`DATA_VALUE` is in tenths of a degree C.** `390` means 39.0 °C. Miss it
   and every number is plausible and ten times wrong.
3. **CEC's `COUNTY_NUM` is not a FIPS code.** It is an alphabetical index
   (Alameda=1, Alpine=2, Amador=3) while Census FIPS runs 001, 003, 005. Join
   on it and you mis-assign nearly every county — quietly. We join on the
   normalised county *name*.

---

## The best teaching moment in the series

Save five minutes for this one. It is more valuable than any individual
feature tour.

`shared/gas_transforms.py` step **T2b** filters to California *before* the big
pivot, instead of after. Moving a 20× data reduction ahead of a wide shuffle
should be a landslide. Measured on real runs:

| | time | cost |
|---|---|---|
| pivot first, filter after | 643 s | $0.3144 |
| filter first (T2b) | 597 s | $0.2919 |

**About 7%.** Byte-identical output — same row count, same histogram.

> "The obvious optimisation returned seven percent. Not because it was wrong —
> it is strictly better and we kept it — but because the pivot was never the
> bottleneck. Both versions still read all two hundred million rows off S3, and
> that I/O dominates. So: where *did* the time go? And the answer is read
> throughput, which is why partition pruning matters here and shuffle tuning
> doesn't."

That is "profile before you optimise", with your own numbers instead of a
slogan. Rooms remember it.

---

## Module 4+ — the ML chain (once you have run it yourself)

```bash
python shared/prepare_ml_data.py          # splits
python 04-training/launch_training.py     # ~3 min, cents
python 05-experiments-tuning/launch_tuning.py
python 07-deployment/deploy_and_infer.py  # auto-deletes its endpoint
```

### ⚠️ Read this before you put an AUC on a slide

The default label gives **AUC 0.9235**. Do not present that as a result. Here is
what it actually is, measured:

| | AUC |
|---|---|
| all features | **0.9235** |
| calendar only (`obs_month`, `season_*`, `is_heating_season`) | 0.9043 |
| weather only (calendar dropped) | 0.8298 |
| **deseasonalised label** (`--deseasonalize`) | **0.5159** |

Feature importance on the default label: `season_Winter` **0.705**, `obs_month`
**0.216**. Everything else — every temperature, HDD, precipitation column —
shares the remaining 0.079.

So the 0.92 is a calendar lookup. The model learned "winter is cold and people
heat their homes." True, and worth nothing. It is **not** leakage — the month is
legitimately known at prediction time — it is a *degenerate task*.

And when you strip the seasonal signal out with `--deseasonalize`, the score
collapses to **0.5159**, i.e. a coin flip. That is the honest diagnosis:

> **The label is a county-MONTH aggregate, but the features are a single
> STATION-DAY.** One day's weather at one station cannot tell you whether a
> whole county-month was unusually high-demand for that time of year. The grain
> does not match.

**The fix** (not yet implemented): aggregate the features to station-month to
match the label's grain — mean/min/max temperature for the month, total HDD,
count of days below freezing, total precipitation. That is also the real
utility-forecasting formulation, and ~3,241 stations × 120 months is still
several hundred thousand rows. Until that is done, treat the ML modules as
**workflow** demos, not modelling results.

### How to use this honestly in class

This is a better segment than a good score would have been. Run it live:

```bash
python shared/prepare_ml_data.py                  # AUC ~0.92
python shared/prepare_ml_data.py --no-calendar    # AUC ~0.83
python shared/prepare_ml_data.py --deseasonalize  # AUC ~0.52
```

> "Our first model scored 0.92 and we were delighted. Then we looked at feature
> importance: seventy percent of it was one column — is it winter. So we asked
> the harder question — was *this* January unusual for this county — and the
> model fell to a coin flip. The lesson isn't that the model was bad. It's that
> the question was easy, and we didn't notice until we checked."

Then show the grain-mismatch diagnosis. That arc — confident number, feature
importance, honest re-framing, root cause — is the single most useful thing an
ML practitioner can watch someone do.

### The leakage lesson — do this one live

CEC consumption is **monthly**, so every daily row inside a county-month
carries the same label. A random row-level split puts rows from the same
county-month on both sides, and the model sees its test labels during training.

`prepare_ml_data.py` splits by **county-month group** by default. To show the
damage:

```bash
python shared/prepare_ml_data.py --random-split   # the wrong way, on purpose
python 04-training/launch_training.py            # note the inflated AUC
python shared/prepare_ml_data.py                 # the honest way
python 04-training/launch_training.py            # note the drop
```

> "That gap is what group leakage buys you. Nothing about the model changed.
> Only the split did."

Expect a modest AUC from the honest split. **Say so.** The point of the series
is the workflow, and a teaching repo that pretends to a great score teaches the
wrong instinct.

---

## After class — teardown

Order matters: cleanup first (it removes things Terraform doesn't manage),
then destroy.

```bash
powershell -File cleanup/cleanup.ps1     # Glue job, apps, endpoints, derived data
cd terraform && terraform destroy && cd ..
python cleanup/verify_teardown.py        # must print CLEAN
```

`verify_teardown.py` is the one that matters. It sweeps endpoints,
Studio/Canvas apps, MLflow servers, notebook instances and EMR Serverless apps
across several regions using boto3, and **any check it cannot run is reported
as UNKNOWN with a non-zero exit** — silence is never treated as success.

Two gotchas it exists to catch:

- Opening Data Wrangler or Canvas auto-creates an EMR Serverless application
  named `sm-canvas-data-wrangler-emr-app-<user-profile>`. Matching on your own
  prefix will never find it. Three of these survived previous teardowns.
- Your AWS CLI (2.15.47) has no `sagemaker list-mlflow-tracking-servers`, so a
  CLI-based check for MLflow servers fails silently. boto3 has it; that is why
  this script is Python.

---

## If something goes wrong mid-demo

| Symptom | Do this |
|---|---|
| Glue job failed | `python 01-data-prep/new-visual-etl/run_glue_job.py --logs` |
| "no rows" from `prepare_ml_data.py` | Module 1 hasn't run — run step 4 |
| Canvas died mid-session | The reaper's 10-hour age cap fired; relaunch it |
| Permissions error anywhere | `python 00-setup/preflight.py` names the fix |
| Cost looks wrong | `python cleanup/verify_teardown.py` lists what's running |

**Have a fallback.** Any live cloud demo can fail on stage for reasons that are
not your fault. `TEST_LOG.md` holds every real number from a verified run — if
a job dies, switch to the log and talk through what it produced. Nobody minds,
as long as you are open that you're showing a recorded result.
