<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 0 — Setup

One-time account setup and dataset staging. Everything else depends on this.

## Run

```bash
python 00-setup/preflight.py
python 00-setup/create_bucket.py
python 00-setup/stage_dataset.py --start-year 2015 --end-year 2024
```

- `preflight.py` — read-only; verifies the account is wired up and names any fix
- `create_bucket.py` — once ever; outside Terraform so `destroy` can never delete the data
- `stage_dataset.py` — ~4 min; 419 Parquet objects + 4 lookups, ~720 MB

## Creates

| | |
|---|---|
`raw/observations/` | GHCN daily weather, `YEAR=`/`ELEMENT=` partitioned
`raw/stations/` | 3,241 California stations
`raw/counties/` | 58 county centroids
`raw/consumption/` | CEC therms by county × month × sector

## Cost

S3 storage only, ~$0.01/month.

## Notes

GHCN already lives in S3, so the observation copy is server-side — no download to go flaky mid-setup.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
