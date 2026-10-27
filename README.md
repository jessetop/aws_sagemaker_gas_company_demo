# SageMaker demo series — gas-utility demand forecasting

Short, instructor-led demos that run the **same real dataset** through every
service in a SageMaker course, on your own AWS account.

Built to sit alongside an AWS-authored curriculum rather than replace it: the
official labs are self-contained and students run those. These are the
five-minute interludes where the instructor shows *this* data in *this* service
— which is what makes a room lean in, because it's a real problem instead of
abalone measurements.

---

## The dataset, in one sentence

> *A gas utility's load is driven by the weather. Take every weather observation
> on earth for ten years, narrow it to California's 3,241 stations, work out how
> cold each county actually got, and line that up against how much gas each
> county burned.*

```
201,486,363 raw worldwide rows  →  1,668,673 California station-days

                         mean therms   mean HDD
outside heating season      35.1 M       3.02
in heating season           49.6 M      14.24
```

41% more gas burned against 4.7× the heating degree days. Heating Degree Days
(base 65°F) is the actual metric utility planners forecast winter load with, so
this is the shape of a real industry problem — not a toy dataset in costume.

### Four public sources, nothing proprietary

| Source | Role | Size |
|---|---|---|
[NOAA GHCN-Daily](https://registry.opendata.aws/noaa-ghcn/) | fact table — daily station weather | 200M+ rows |
GHCN station metadata | dimension — 3,241 California stations | 180 KB |
[US Census 2020 Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html) | dimension — 58 county centroids | 4 KB |
[CEC QFER](https://www.energy.ca.gov/files/energy-consumption-data-files) | label source — therms by county × month × sector | 3 MB |

GHCN already lives in S3, so staging is a server-side copy. Full licensing and
attribution in [`DATA_SOURCES.md`](DATA_SOURCES.md).

---

## Start here

```bash
cp demo.env.example demo.env       # set account, region, profile, bucket
python 00-setup/preflight.py       # read-only; tells you exactly what to fix

python 00-setup/create_bucket.py   # once, ever — outside Terraform on purpose
cd terraform && terraform apply && cd ..

python shared/prebake_demos.py --all     # ~46 min, a few dollars, unattended
python shared/verify_demos.py            # confirm every artifact is real
```

Then read [`DEMOS.md`](DEMOS.md) for the demo scripts, or
[`DAY1_RUNBOOK.md`](DAY1_RUNBOOK.md) / [`DAY2_RUNBOOK.md`](DAY2_RUNBOOK.md) for
click-by-click instructions.

---

## The cooking-show pattern

A training job takes 3 minutes. An HPO sweep takes 15. Clarify SHAP takes 12.
Nobody watches a progress bar, and a demo that depends on a live job finishing
is a demo that can fail in front of a room. So every demo is:

> **1.** Show the console where you'd configure it
> **2.** Hit cancel — *"this takes twelve minutes, I won't make you watch"*
> **3.** Cut to the one that's already finished, and talk about the **result**

`shared/prebake_demos.py` bakes those finished artifacts beforehand.
`shared/verify_demos.py --status` tells you what exists, where it is, and the
command to rebuild anything missing — run it the morning of.

---

## What's here

| Demo | Service | Status |
|---|---|---|
1 | Studio + the data in S3 | ✅ |
2 | **Data Wrangler** — catching a target leak | ✅ F1 1.0 → 0.675 |
3 | **PySpark on Glue Interactive Sessions** (no EMR cluster) | ✅ $0.07 |
4 | **SageMaker Processing** — the substrate the others run on | ✅ |
5 | **Feature Store** | ✅ |
6 | Training jobs | ✅ auc 0.9235, 145 s |
7 | **Experiments** — and an honest look at the metric | ✅ |
8 | Hyperparameter tuning | ✅ best 0.9365 |
9 | **Clarify** — bias + SHAP | ✅ |
10 | Deployment + inference | ✅ self-deleting endpoint |
11 | **Autopilot** | ✅ 0.8800 vs hand-built 0.8794 |
12 | **Model Monitor** + Model Card | ✅ runs at $0 from artifacts |

Not ported: module 10 (custom container).

---

## Three demos worth the price of admission

**Demo 2 — the tool catches your leak.** `heating_day` is defined as
`temp_max_c < 18.33`, and `temp_max_c` was left in the features. Quick Model
scores **F1 = 1.0** and Data Wrangler flags target leakage unprompted. Switch to
the companion flow with that column dropped: **F1 = 0.675**. A genuine mistake,
caught by the product, on the client's own data.

**Demo 7 — your metric is lying and here's how you find out.** The model scores
**AUC 0.9235**. Then look at feature importance: `season_Winter` is **0.705** of
it. Ask the harder question — was *this* January unusual for this county's
Januaries — and it collapses to **0.5159**. A coin flip. Root cause: the label
is a county-*month* aggregate while the features are a single station-*day*. The
grain doesn't match, and no amount of tuning fixes a question asked at the wrong
resolution.

**Demo 3 — Simpson's paradox, live.** Within each county, degree-days and therms
correlate **+0.72 average** (top counties 0.88–0.91). Pool all 47 counties into
one correlation and it becomes **−0.0088**. Same rows, opposite conclusion.

---

## Cost

The whole series costs a few dollars. One service will hurt you:

> 🔴 **SageMaker Canvas bills ~$32–64/day and keeps billing after you close the
> browser tab** — you have to delete the *app*. One forgotten session was $202
> of a $218 month.

`terraform/canvas_reaper.tf` deploys a Lambda that deletes idle Canvas apps
hourly across multiple regions, measuring idle from `DescribeApp`'s
`LastUserActivityTimestamp` so it never kills a session you're using. Plus a
daily budget, a SageMaker-only monthly budget with a forecast alert, and cost
anomaly detection.

Teardown:

```bash
powershell -File cleanup/cleanup.ps1     # jobs, apps, endpoints
cd terraform && terraform destroy        # domain, reaper, budgets, IAM
python cleanup/verify_teardown.py        # must print CLEAN
```

**`terraform destroy` never deletes the bucket or the datasets** — the bucket is
deliberately outside Terraform's lifecycle, so teardown after class doesn't cost
you a 25-minute rebuild.

`verify_teardown.py` is boto3 rather than CLI-based on purpose: the AWS CLI on
the authoring machine had no `list-mlflow-tracking-servers`, so a CLI-based
check failed silently while printing "nothing billable found". Any check it
cannot run is reported as UNKNOWN with a non-zero exit. Silence is never treated
as success.

---

## Layout

```
00-setup/          preflight, bucket creation, dataset staging
01-data-prep/      Data Wrangler flows (+ generator), Glue Visual ETL
02-processing/     PySpark deep dive on serverless Spark
03-feature-store/  feature group + ingest
04-training/       estimator launcher + the training script
05-experiments-tuning/
06-clarify-.../    bias + explainability
07-deployment/     deploy/infer, and the monitoring endpoint
08-pipelines/      the full DAG: process → bias → train → eval → register
09-autopilot/      AutoML leaderboard
10-custom-container/  bring-your-own-container  (not ported)
shared/            config, transforms, ML prep, prebake, verification
cleanup/           teardown + the billable-resource sweep
terraform/         domain, Canvas reaper, budgets, IAM
```

`shared/gas_transforms.py` is the single source of truth for the pipeline — the
same PySpark runs on Glue, EMR Serverless, a Studio notebook, or local Spark.

---

## Honest limitations

- **The model does not usefully predict anything yet.** See Demo 7: the label's
  grain doesn't match the features'. Fixing it means aggregating features to
  station-month. Until then the ML modules are **workflow** demos, not
  modelling results, and `DEMOS.md` says so.
- **Module 10 (custom container) is not ported.**
- `TEST_LOG.md` records only what was actually executed, with real numbers.
  Anything absent from it has not been run.
