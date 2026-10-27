# Terraform — populate us-east-1 domains + Canvas cost guard

This stack provisions the **supporting infra** for the demo in **us-east-1**, where
the live SageMaker + Unified Studio domains already exist. It deliberately does
**not** create or modify any SageMaker/Unified Studio **domain** — those are
referenced by ID only.

## What it creates

| Resource | Purpose |
|---|---|
| S3 bucket `YOUR-BUCKET-NAME` | In-region copy of the project dataset (data currently lives in the us-east-2 bucket). |
| IAM policy on existing `roi-smdemo-exec-role` | Grants the demo exec role read/write on the new bucket. |
| Lambda `roi-smdemo-canvas-reaper` + EventBridge rule | **Cost guard:** hourly, deletes idle Canvas apps so they can't bill ~$50/day. |

## What it does NOT touch
- No `aws_sagemaker_domain` / no DataZone domain — existing domains referenced via
  `sagemaker_domain_id` / `datazone_domain_id` variables only.
- The existing exec role is referenced with a `data` source, not recreated.

## Usage

```pwsh
cd terraform
terraform init
terraform plan          # review — should add S3 + IAM policy + Lambda/EventBridge only
terraform apply
```

After apply, sync the data and populate (see repo root scripts):

```pwsh
# copy ~385 MB us-east-2 -> us-east-1
../shared/sync_data_to_us_east_1.ps1

# stage dataset + Feature Store group in us-east-1
python ../00-setup/stage_dataset.py --bucket YOUR-BUCKET-NAME --region us-east-1 --profile default
```

## Canvas cost guard knobs (terraform.tfvars)
- `canvas_max_idle_minutes` — idle threshold before a Canvas app is killed (default 60).
- `canvas_reaper_schedule` — how often to check (default `rate(1 hour)`).
- `kill_app_types` — which AppTypes to reap (default `Canvas`; JupyterLab excluded).
- `canvas_reaper_enabled = false` disables the scheduled reaper (the manual
  `cleanup/kill_canvas.*` script still works).

State is **local** by default (`terraform.tfstate` in this dir). Do not commit it.
