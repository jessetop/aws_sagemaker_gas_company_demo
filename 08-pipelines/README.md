<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 8 — SageMaker Pipelines

The full DAG: process → data-bias check → train → evaluate → conditional register.

## Run

```bash
python 08-pipelines/build_pipeline.py
python 08-pipelines/build_pipeline.py --start
```

- `build_pipeline.py` — upserts the definition (no compute, free)
- `build_pipeline.py --start` — executes it

## Creates

| | |
|---|---|
pipeline | `<prefix>-pipeline`, plus `pipeline/` outputs in S3
registry | a new **Approved** version in `<prefix>-models`

## Cost

**~$0.16 per full execution**, ~36 minutes wall clock. Measured by
instance-second arithmetic over execution `p9khxwja52g2` (2026-10-27); this file
previously estimated "a few dollars," which was ~20× high. The two Clarify model
checks dominate — each runs a shadow endpoint alongside the processing job.

Both shadow endpoints tear themselves down on success. A *failed* Clarify step
can orphan one, so check `list-endpoints` if a run breaks.

## Notes

`preprocess.py` reads `processed/visual-etl/`, **not** `raw/`. The heavy reshaping happens once in Spark; this step only does the cheap tabular ML prep. Its `FEATURES` list must stay in lockstep with `build_pipeline.py` because the Clarify steps declare headers from it.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
