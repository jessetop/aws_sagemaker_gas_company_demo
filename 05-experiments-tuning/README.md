<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 5 — Experiments and tuning

Experiment tracking plus a Bayesian hyperparameter sweep.

## Run

```bash
python 05-experiments-tuning/launch_tuning.py
python shared/populate_studio_classic.py
```

- `launch_tuning.py` — ~15 min, ~$1 for 4 trials
- `populate_studio_classic.py` — logs the baseline + trials into an Experiment; metadata only, no compute

## Creates

| | |
|---|---|
tuning job | `<prefix>-hpo-...` with a candidate leaderboard
experiment | `<prefix>-experiment`, 5 runs with parameters and metrics

## Cost

~$1. `max_parallel` is a speed dial; `max_jobs` is the cost dial.

## Notes

Measured: baseline 0.9235, best trial 0.9365. Four jobs for 1.3 points — on this problem the hyperparameters barely matter, which you only know because you ran the sweep and looked.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
