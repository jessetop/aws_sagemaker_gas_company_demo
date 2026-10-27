"""
Module 10 — run the CUSTOM container as a SageMaker training job (scale-out).

The exact image you built and pushed to ECR (see build_and_push.sh) now runs on
managed SageMaker infrastructure against the full dataset in S3. Same image that
ran on your laptop (run_local.sh) — this is the "build once, scale out" payoff:

    laptop (docker run)  ->  ECR (docker push)  ->  SageMaker (this script)

SageMaker pulls the image from ECR, mounts the S3 channels at /opt/ml/input/data,
runs `docker run <image> train`, and uploads /opt/ml/model to S3.

Usage:
    python launch_sagemaker_training.py
    python launch_sagemaker_training.py --image-uri 000000000000.dkr.ecr.us-east-1.amazonaws.com/roi-smdemo-custom-train:latest
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args, ACCOUNT

REPO = "roi-smdemo-custom-train"


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument("--image-uri", default=None, help="ECR image (defaults to the demo repo:latest)")
    p.add_argument("--instance-type", default="ml.m5.large")
    p.add_argument("--prefix", default="ml/gas")
    args = p.parse_args()

    image_uri = args.image_uri or (
        f"{ACCOUNT}.dkr.ecr.{args.region}.amazonaws.com/{REPO}:latest"
    )
    print("image:", image_uri)

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)
    b = args.bucket

    # Note: no entry_point / source_dir here — unlike the framework estimators
    # elsewhere in the repo, the training code lives INSIDE the image.
    estimator = Estimator(
        image_uri=image_uri,
        role=args.role_arn,
        instance_count=1,
        instance_type=args.instance_type,
        sagemaker_session=sm_sess,
        base_job_name="roi-smdemo-custom-train",
        # Delivered to the container as /opt/ml/input/config/hyperparameters.json.
        hyperparameters={"learning-rate": 0.1, "n-estimators": 150, "max-depth": 3},
        metric_definitions=[
            {"Name": "validation:auc", "Regex": "validation_auc=([0-9\\.]+)"},
            {"Name": "validation:accuracy", "Regex": "validation_accuracy=([0-9\\.]+)"},
        ],
        tags=[{"Key": "Project", "Value": "sagemaker-unified-studio-demos"}],
    )

    inputs = {
        "train": TrainingInput(f"s3://{b}/{args.prefix}/train/", content_type="text/csv"),
        "validation": TrainingInput(f"s3://{b}/{args.prefix}/validation/", content_type="text/csv"),
    }

    try:
        estimator.fit(inputs, logs=True)
    except Exception as exc:
        try:
            desc = boto_sess.client("sagemaker").describe_training_job(
                TrainingJobName=estimator.latest_training_job.name
            )
            print("TRAINING FAILED:", desc.get("FailureReason", str(exc)))
        except Exception:
            print("TRAINING FAILED:", exc)
        return 1

    print("model artifact:", estimator.model_data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
