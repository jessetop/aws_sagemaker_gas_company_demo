<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 2 — Scalable processing

PySpark on **serverless** Spark. No EMR cluster: Glue Interactive Sessions bill per second with nothing to tear down.

## Run

```bash
python 02-processing/pyspark-deep-dive/run_spark_analysis.py --start
```

- `run_spark_analysis.py` — runs the analysis as a Glue job to verify it (~$0.07)

## Creates

| | |
|---|---|
`code/pyspark-deep-dive/` | the notebook and script, staged for JupyterLab

## Cost

~$0.07 for a 5-minute interactive session. `%idle_timeout 15` in the first cell is the only guard — the Canvas reaper does **not** catch Glue sessions.

## Notes

See [`pyspark-deep-dive/README.md`](pyspark-deep-dive/README.md) for the eight sections. The AWS lab already covers connecting Studio to an EMR cluster; this covers the DataFrame work the labs skip.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
