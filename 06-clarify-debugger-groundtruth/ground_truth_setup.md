# Module 6C — Ground Truth labeling (conceptual / not auto-tested)

Ground Truth produces the labels you'd otherwise not have. Our dataset already
has the `high_demand` label (derived in the pipeline), so we teach Ground Truth as
"here's how you'd have *created* a label like this from unlabeled data." It isn't
run live because labeling needs a human workforce — not a cheap unattended job.

## Old way — SageMaker AI

1. **Input manifest** in S3 — one JSON line per item to label:
   ```json
   {"source-ref": "s3://.../observations/row-000123.json"}
   ```
2. **Labeling job** (`aws sagemaker create-labeling-job`) with:
   - a **task type** (image/text classification, bounding box, custom),
   - a **UI template** (Liquid HTML worker task template),
   - a **workforce**: private (your own labelers), a vendor, or Mechanical Turk,
   - a **pre/post-processing Lambda** for custom flows.
3. Output is an **augmented manifest** in S3 with the labels appended, ready to
   feed training (Module 4).

Skeleton:
```bash
aws sagemaker create-labeling-job \
  --labeling-job-name <prefix>-label \
  --label-attribute-name high_demand \
  --input-config '{"DataSource":{"S3DataSource":{"ManifestS3Uri":"s3://.../manifest.jsonl"}}}' \
  --output-config '{"S3OutputPath":"s3://.../ground-truth/"}' \
  --role-arn arn:aws:iam::000000000000:role/roi-smdemo-exec-role \
  --human-task-config file://human-task-config.json \
  --profile default --region us-east-2
```

## New way — Unified Studio

The same Ground Truth labeling jobs run, but the **output augmented manifest lands
as a governed data asset** in the project catalog — discoverable and lineage-linked
to any model trained on it, instead of being a loose S3 path you have to remember.

## Talking points
- Labeling is the *source* of the supervised target everything downstream needs.
- Old way: you wire manifest + template + workforce + output path yourself.
- New way: same machinery, but the labeled dataset is catalogued and governed.
