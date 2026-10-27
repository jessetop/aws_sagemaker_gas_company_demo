<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 8 — SageMaker Pipelines

The full DAG: process → data-bias check → train → evaluate → conditional register.

## Run

```bash
python 08-pipelines/build_pipeline.py
python 08-pipelines/build_pipeline.py --start
```

- `build_pipeline.py` — defines the pipeline (no compute)
- `build_pipeline.py` — executes it

## Creates

| | |
|---|---|
pipeline | `<prefix>-pipeline`, plus `pipeline/` outputs in S3

## Cost

A few dollars per full execution.

## Notes

`preprocess.py` reads `processed/visual-etl/`, **not** `raw/`. The heavy reshaping happens once in Spark; this step only does the cheap tabular ML prep. Its `FEATURES` list must stay in lockstep with `build_pipeline.py` because the Clarify steps declare headers from it.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
