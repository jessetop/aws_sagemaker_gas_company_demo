# Studio Classic ↔ Unified Studio — the crosswalk

The teaching reference: for each capability, **where it lives in SageMaker Studio
Classic (the old way)** and **where the same thing lives in SageMaker Unified
Studio (the new way)** — so you can show "here it is… and here's the same thing
over here." The last column points at the demo module that exercises it.

> **Two mental models.** *Studio Classic* is a single ML IDE bolted onto the
> SageMaker AI service; every tool is a panel in one app, and data/catalog live
> elsewhere (S3, Glue console). *Unified Studio* is a **project-scoped portal**:
> data, analytics (Glue/Athena/EMR), ML, and GenAI in one governed place, with a
> catalog and lineage. Same underlying services — different organizing principle.

---

## The big map

| # | Capability | **Studio Classic** (old) — where | **Unified Studio** (new) — where | Demo |
|---|---|---|---|---|
| 1 | Interactive data prep (low-code) | Left nav → **Data Wrangler** (or **Canvas → Data prep**) | Project → **Build → Visual ETL** (drag-drop, Glue-backed) | [01](01-data-prep/) |
| 2 | Scalable processing (Spark/EMR) | Notebook + **SparkMagic/EMR** connection you wire up | Project → **Build → JupyterLab** on a **Spark connection** (Glue IS / EMR Serverless); or **Query Editor** for SQL | [02](02-processing/) |
| 3 | Data discovery / catalog | *(not in Classic)* — Glue Data Catalog in the AWS console | Project → **Discover → Catalog** (search assets, subscribe, lineage) | [03](03-feature-store/) |
| 4 | Feature Store | Left nav → **Feature Store** | Project → **Build → ML** (SageMaker Studio app) → **Feature Store**; groups also appear as **catalog assets** | [03](03-feature-store/) |
| 5 | Custom training jobs | SDK in a notebook → view in **Experiments/Training** panel | Same SDK in a **project** notebook → view in project **ML → Training jobs**; role+bucket supplied by project | [04](04-training/) |
| 6 | Experiment tracking | Left nav → **Experiments and trials** (SageMaker Experiments) | **Managed MLflow** (launched from the project) | [05](05-experiments-tuning/) |
| 7 | Hyperparameter tuning | SDK tuner → **Hyperparameter tuning jobs** | Same tuner from a project notebook → trials in **MLflow** | [05](05-experiments-tuning/) |
| 8 | Model registry | Left nav → **Model registry** | Project **ML → Models** / catalog (governed, shareable) | [04](04-training/) |
| 9 | Bias & explainability (Clarify) | Clarify job → **report.html** you open from S3/Studio | Reports surface on the **model** in the project ML view | [06](06-clarify-debugger-groundtruth/) |
| 10 | Training debug/profiling | **Debugger** insights on an experiment/trial | **Profiler** insights in the project training-job view | [06](06-clarify-debugger-groundtruth/) |
| 11 | Data labeling | **Ground Truth** (AWS console / SDK) → manifest in S3 | Same Ground Truth → output lands as a **catalog data asset** | [06](06-clarify-debugger-groundtruth/) |
| 12 | Real-time deployment | Left nav → **Endpoints** / `model.deploy()` | Project **ML → Endpoints** / one-click deploy, governed | [07](07-deployment/) |
| 13 | The notebook IDE | **Studio Classic** JupyterLab (standalone) | **JupyterLab** inside a project (governed, Git-backed) | all |
| 14 | Foundation models / GenAI | **JumpStart** | **Build → GenAI** app/playground + Bedrock, in-project | — |
| 15 | AutoML / model ranking | **Autopilot** via SDK or Studio Classic Autopilot UI (low-code) | **SageMaker Canvas** — no-code, in Unified Studio | [09](09-autopilot/) |

> **Autopilot vs Canvas — one engine, three front doors.** Autopilot is the AutoML
> *engine* (`CreateAutoMLJobV2`). You drive it via the **SDK** (code), the **Studio
> Classic Autopilot UI** (low-code), or **Canvas** (no-code). All produce the same
> ranked candidate leaderboard. The demo's `09-autopilot/launch_autopilot.py` uses
> the SDK; show Canvas live for the no-code "new way" (remember: Canvas app is a
> billable running session — stop it after).

---

## How to demo the compare-and-contrast (per capability)

For each row, the 30-second script is the same shape:

1. **Show it in Classic.** Open the Studio Classic panel (e.g. Data Wrangler),
   point at the thing.
2. **Show it in Unified Studio.** Open the project equivalent (e.g. Visual ETL),
   point at the *same* thing.
3. **Name the difference.** Usually one of: *governed vs loose*, *project vs
   account*, *catalogued vs find-it-yourself*, *managed runtime vs you-wire-it*.

### The three differences that repeat
- **Governance**: Unified Studio wraps everything in a **project** with a role,
  catalog, lineage, and permissions. Classic gives you raw service resources.
- **Unification**: data + ETL + ML + GenAI share one portal in Unified Studio;
  Classic is ML-only and sends you to other consoles for data.
- **Same engines underneath**: Glue, EMR, training jobs, Feature Store, endpoints
  are the *same APIs* — so skills transfer; only the front door changes.

---

## Where the demo artifacts live

`python shared/verify_demos.py` prints, for every artifact: whether it exists,
its real row/record counts, the S3 URI or console path, and the command to
rebuild it. That is authoritative; a table here would go stale the first time
anything is re-run.

The honest teaching point this section used to make is still worth keeping: a
training job created by the SDK with a standalone role is a loose **service
resource**. The same artifact created inside a Unified Studio project is a
governed **project asset** with a catalog entry and lineage. Same API, same
compute — different organising principle. That gap *is* the lesson.

## Accuracy caveat (read before teaching)

Unified Studio's menu labels evolve release-to-release. The **capability mapping**
above is stable; exact **left-nav wording** ("Build → Visual ETL", "ML →
Endpoints") may differ slightly in your domain's version. Verify the precise click
path live before class — or ask me to screenshot-verify each path against your
domain via the console.
