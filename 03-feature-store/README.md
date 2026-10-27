<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 3 — Feature Store

A feature group over the engineered weather features, so `hdd65` is defined once and consumed by everyone — the same definition at training time and at inference time.

## Run

```bash
python 03-feature-store/feature_store_ingest.py
```

- `feature_store_ingest.py` — ~3 min, cents

## Creates

| | |
|---|---|
feature group | `<prefix>-features`, record id `observation_id`
`feature-store/` | offline store as Parquet, queryable via its Glue table

## Cost

Cents. The offline store is just S3.

## Notes

Online store is currently **off** — offline only. That means no low-latency `GetRecord` lookup, so the training/serving-skew point is assertable but not demonstrable. Enabling it needs the group recreated.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
