# Module 6 — Ground Truth, Clarify & Debugger: SageMaker AI vs Unified Studio

**~5 minutes each** (three short sub-demos). The "supporting cast" of responsible
ML, shown old-way and new-way.

## A. Clarify — bias & explainability  ✅ live-testable
```bash
python clarify_bias_explainability.py \
  --model-name roi-smdemo-taxi-model \
  --bucket roi-smdemo-029331796573-us-east-2 \
  --role-arn arn:aws:iam::029331796573:role/roi-smdemo-exec-role \
  --profile roitraining --region us-east-2 \
  --facet is_airport_trip --analysis-rows 300
```
- Runs a Clarify processing job: **pre/post-training bias** on a facet (e.g.
  airport vs non-airport trips) and **SHAP** feature attributions.
- **Cost guard:** SHAP evaluates the model ~`num_samples` times *per row* via an
  internal shadow endpoint, so it scales with `--analysis-rows`. Keep it small
  (a few hundred) for the demo — the full test set is millions of inferences.
- **New way:** the same bias/explainability reports attach to the model in the
  Unified Studio asset/model view, next to lineage — instead of digging in S3.

## B. Debugger — training insight  ✅ live-testable
```bash
python 06-clarify-debugger-groundtruth/launch_debugger_xgboost.py --num-round 60
```
- Runs a **built-in XGBoost** training job on the SAME `high_tip` task/data with
  `DebuggerHookConfig` + built-in `Rule`s (`LossNotDecreasing`, `Overfit`).
  Debugger auto-captures tensors: a **loss curve** (train/validation logloss per
  round), **feature_importance**, and **average_shap**. Open the job in
  **SageMaker AI Studio → Training → [job] → Debugger** to see charts + rule outcomes.
- **Why XGBoost, not our sklearn model?** Debugger only natively instruments
  XGBoost / PyTorch / TF / MXNet. A custom scikit-learn script (our `train.py`)
  emits no tensors, so the rules would show *no data*. XGBoost is the same task on
  the same pipeline CSVs, and is the canonical Debugger demo.
  ([`debugger_snippet.py`](debugger_snippet.py) shows the sklearn-estimator kwargs
  conceptually, but produces no tensor data for a one-shot `.fit()`.)
- **New way:** Unified Studio surfaces training insights/profiling in the project
  training view; the SageMaker Profiler replaces much manual hook wiring.
- Talking point: Debugger/Profiler are about *why training behaves as it does*;
  the new experience makes them part of the governed run rather than opt-in code.
  In our run the `LossNotDecreasing` rule fired (`IssuesFound`) — a live example
  of Debugger flagging a training pathology automatically.

## C. Ground Truth — labeling
- **Old way:** create a labeling job pointed at a manifest in S3, with a label
  task template and a workforce (private/vendor/Mechanical Turk). See
  [`ground_truth_setup.md`](ground_truth_setup.md). *Not auto-tested here* — it
  needs human labelers, which isn't a cheap unattended run.
- **New way:** the same Ground Truth jobs, with outputs landing as governed data
  assets in the project catalog.
- Our dataset is already labeled (`high_tip`), so Ground Truth is taught
  conceptually: "this is how you'd have produced that label from raw data."

## Old vs new — talking points
| | SageMaker AI | Unified Studio |
|---|---|---|
| Bias/explain | Clarify job → S3 reports | reports on the model asset |
| Training insight | Debugger hooks/rules | profiling in project view |
| Labeling | Ground Truth console/SDK | same, outputs catalogued |

## Cost & cleanup
Clarify is one short processing job (cents). Debugger adds negligible cost to a
training run. Ground Truth cost depends on the workforce (we don't run it live).
