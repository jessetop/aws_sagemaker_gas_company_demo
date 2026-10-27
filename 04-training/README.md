<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 4 — Custom training jobs

A scikit-learn GradientBoosting classifier launched through the SageMaker Python SDK. `train.py` doubles as the inference entry point.

## Run

```bash
python 04-training/launch_training.py
```

- `launch_training.py` — ~4 min, cents

## Creates

| | |
|---|---|
training job | `<prefix>-train-...`, with the model artifact in S3

## Cost

145 billable seconds on `ml.m5.large`.

## Notes

The whole SageMaker contract is three env vars and a print statement: `SM_CHANNEL_TRAIN`, `SM_MODEL_DIR`, and metrics as `name=value` on stdout. Read DEMOS.md **Demo 7** before quoting the AUC.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
