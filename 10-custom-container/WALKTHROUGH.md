# Module 10 — Bring Your Own Container: laptop → ECR → SageMaker

**~10 minutes.** Teaches Docker containers for ML: what SageMaker actually expects
of a training container, how the *same* image runs on a laptop and scales out on
managed infrastructure. Uses the taxi `high_tip` classifier (custom scikit-learn).

## The one idea
A SageMaker training container is just an image with an executable named **`train`**
on the PATH. SageMaker runs `docker run <image> train` and mounts data/config into
fixed paths. Build it once; run it anywhere.

```
   your laptop            ECR (registry)          SageMaker (managed)
  docker build   ─────▶   docker push   ─────▶   pull + docker run train
  docker run train         (image)                on ml.m5.large + S3 data
```

## Files
| File | What it shows |
|---|---|
| `container/Dockerfile` | the whole contract — install deps, drop `train` on PATH |
| `container/train` | the SageMaker container contract: reads `/opt/ml/input`, writes `/opt/ml/model` |
| `build_and_push.sh` / `.ps1` | build → create ECR repo → login → tag → push |
| `run_local.sh` / `.ps1` | run the identical image on your laptop (no AWS) |
| `launch_sagemaker_training.py` | run the identical image on SageMaker against S3 data |
| `sample-data/` | ~400 rows bundled so the local run needs zero cloud |

## Demo script

### 1. Look at the contract (30s)
Open `container/Dockerfile` and `container/train`. Point out: no framework — SageMaker
runs `docker run image train`; the script reads `/opt/ml/input/data/{train,validation}`,
hyperparameters from `/opt/ml/input/config/hyperparameters.json`, writes `/opt/ml/model`.

### 2. Build it (2 min)
```bash
# Windows:  .\build_and_push.ps1        Linux/Mac:  ./build_and_push.sh
```
Watch the layers build. This is a normal `docker build` — nothing SageMaker-specific yet.

### 3. Run it on your laptop (1 min)
```bash
# Windows:  .\run_local.ps1             Linux/Mac:  ./run_local.sh
```
The container trains on the bundled sample and writes `local-output/model/model.joblib`.
Key point: **it ran with no cloud** — because we own the whole environment.

### 4. Show it in ECR (1 min)
The build script already pushed it. In the console: **ECR → Repositories →
`roi-smdemo-custom-train`** → the `latest` image + its digest/size. Or:
```bash
aws ecr describe-images --repository-name roi-smdemo-custom-train --profile roitraining --region us-east-1
```

### 5. Scale it out on SageMaker (5 min)
```bash
python launch_sagemaker_training.py
```
SageMaker pulls the image from ECR, provisions an `ml.m5.large`, streams the full
S3 train/validation channels in, runs the **same** `train`, and uploads the model to
S3. Watch the same `validation_auc=…` line you saw locally — identical code, managed
scale. The job appears under **Training → Training jobs** (`roi-smdemo-custom-train-…`).

## Old vs new — talking point
- **Old way (here):** you build + push the image and point an estimator at the ECR URI.
- **New way (Unified Studio):** the same custom image is registered/governed in the
  project and launched from the project — identical container, governed lineage.

## Cost & cleanup
Local build/run is free. The SageMaker job is one short `ml.m5.large` run (cents).
Remove the ECR image + repo when done:
```bash
aws ecr delete-repository --repository-name roi-smdemo-custom-train --force --profile roitraining --region us-east-1
```
