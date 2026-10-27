<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# Module 6 — Clarify, Debugger, Ground Truth

Pre- and post-training bias metrics plus SHAP feature attribution.

## Run

```bash
python shared/create_model.py
python 06-clarify-debugger-groundtruth/clarify_bias_explainability.py --model-name <prefix>-model
```

- `create_model.py` — free; Clarify needs a Model to run against
- `clarify_bias_explainability.py` — ~12 min, ~$0.50

## Creates

| | |
|---|---|
`clarify/` | bias and SHAP reports as `report.html` / `.pdf` / `analysis.json`

## Cost

~$0.50. SHAP cost scales with rows × samples, so we sample 300 rows — the full test set would be millions of inferences through a shadow endpoint.

## Notes

Bias facet is `is_heating_season`: a demand model that is only accurate half the year fails exactly when a utility needs it. Clarify runs **as a Processing job** — that is where you find it in the console.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY1_RUNBOOK.md`](../DAY1_RUNBOOK.md), [`../DAY2_RUNBOOK.md`](../DAY2_RUNBOOK.md) · Transform contract: [`../PIPELINE_SPEC.md`](../PIPELINE_SPEC.md)
