<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 9 — Autopilot / AutoML

AutoML over the same splits, producing a ranked candidate leaderboard.

## Run

```bash
python 09-autopilot/launch_autopilot.py
python 09-autopilot/launch_autopilot.py --leaderboard
```

- `launch_autopilot.py` — ~30 min, a few dollars
- `launch_autopilot.py` — print the ranking

## Creates

| | |
|---|---|
AutoML job | `<prefix>-autopilot`, 10 candidates, ENSEMBLING mode

## Cost

A few dollars for 10 candidates.

## Notes

Autopilot is the engine; the SDK, the Studio UI and Canvas are three front doors to it. Measured: best candidate 0.8800 accuracy against the hand-built model's 0.8794 — and it inherited the same label, so it is efficiently solving the same slightly-wrong problem.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
