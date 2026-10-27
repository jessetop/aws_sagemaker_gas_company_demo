<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 10 — Bring your own container

A custom training container built on an AWS deep-learning base image.

## Run

```bash
bash 10-custom-container/run_local.sh
bash 10-custom-container/build_and_push.sh
```

- `run_local.sh` — verify the entrypoint locally first
- `build_and_push.sh` — build and push to ECR

## Creates

| | |
|---|---|
ECR image | the custom training container

## Cost

ECR storage plus whatever the training job uses.

## Notes

⚠️ **Not ported to the gas dataset.** This module still carries the original taxi-era training script and sample data was removed. Treat it as a container-mechanics reference, not a working demo.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
