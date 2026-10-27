<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 7 — Deployment, inference and monitoring

A serverless endpoint that deletes itself, and a real-time endpoint with data capture for Model Monitor.

## Run

```bash
python 07-deployment/deploy_and_infer.py
python 07-deployment/monitor_demo_endpoint.py
python 07-deployment/monitor_demo_endpoint.py --delete
```

- `deploy_and_infer.py` — deploys, sends 3 inferences, deletes the endpoint — all in one pass
- `monitor_demo_endpoint.py` — real-time endpoint with 100% data capture + a Model Card
- `monitor_demo_endpoint.py` — tear it down

## Creates

| | |
|---|---|
`ml/gas/datacapture/` | captured inferences as JSONL — input, prediction, timestamp
model card | `<prefix>-demand-classifier`, from the real training metrics

## Cost

🔴 `monitor_demo_endpoint.py` leaves an endpoint billing ~$0.13/hr until deleted. **Endpoints are not caught by the Canvas reaper.**

## Notes

Data capture only works on real-time, instance-backed endpoints — serverless cannot capture, so monitoring decides your endpoint type before cost does. The captured records and Model Card **outlive the endpoint**, so Demo 12 can run at $0 from artifacts alone.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
