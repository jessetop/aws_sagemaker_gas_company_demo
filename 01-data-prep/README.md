<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 1 — Interactive data prep

The same cleaning and enrichment two ways: Data Wrangler (low-code, inside Canvas) and Glue Visual ETL (the Glue-backed canvas).

## Run

```bash
python 01-data-prep/old-data-wrangler/build_flows.py
python 01-data-prep/new-visual-etl/run_glue_job.py --start --workers 4
```

- `build_flows.py` — renders the .flow templates with your bucket and uploads them
- `run_glue_job.py` — ~10 min, ~$0.30; runs the full pipeline

## Creates

| | |
|---|---|
`processed/visual-etl/` | 1,668,673 rows, 25 columns, partitioned by year+month
`flows/*.flow` | two Data Wrangler flows, importable from S3

## Cost

~$0.30 per Glue run. Data Wrangler means a billable Canvas session — `cleanup/kill_canvas.ps1` when done.

## Notes

The committed `.flow` files carry `YOUR-BUCKET-NAME` and are rendered by `build_flows.py` — Data Wrangler cannot read `demo.env`, so the paths inside a flow have to be literal. See **Demo 2** in DEMOS.md for the target-leakage arc the two flows exist to show.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
