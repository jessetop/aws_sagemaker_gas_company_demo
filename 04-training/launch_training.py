"""
Module 4 — launch the gas-demand classifier as a SageMaker training job.

This is the OLD-way launcher: the SageMaker Python SDK `SKLearn` estimator pointed
at our custom `train.py`, run on the cheapest practical instance. The NEW way runs
the *same* estimator code from a Unified Studio project notebook — the training
job API is identical; what changes is that the project supplies the role, tracks
the run in the catalog, and governs lineage. (See WALKTHROUGH.md.)

Demonstrates Kiro Req 5: Estimator with role/entry_point/instance, fit() on S3
channels, 3 hyperparameters, log streaming, model-artifact retrieval, and failure
handling.

Usage:
    python launch_training.py --bucket YOUR-BUCKET-NAME \
        --role-arn arn:aws:iam::000000000000:role/roi-smdemo-exec-role \
        --profile default --region us-east-1
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker.inputs import TrainingInput
from sagemaker.sklearn.estimator import SKLearn

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument("--instance-type", default="ml.m5.large")  # cheapest practical
    p.add_argument("--prefix", default="ml/gas")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)
    b = args.bucket

    # Estimator: custom script, framework container, single cheap instance.
    estimator = SKLearn(
        entry_point="train.py",
        source_dir="04-training",
        role=args.role_arn,
        instance_type=args.instance_type,
        instance_count=1,
        framework_version="1.2-1",
        sagemaker_session=sm_sess,
        base_job_name=config.resource("train"),
        # Three hyperparameters passed through to train.py (Kiro Req 5.3).
        hyperparameters={
            "learning-rate": 0.1,
            "n-estimators": 150,
            "max-depth": 3,
        },
        # Metric definitions scrape the `name=value` lines train.py prints.
        metric_definitions=[
            {"Name": "validation:accuracy", "Regex": "validation_accuracy=([0-9\\.]+)"},
            {"Name": "validation:auc", "Regex": "validation_auc=([0-9\\.]+)"},
        ],
        tags=[{"Key": "Project", "Value": "sagemaker-unified-studio-demos"}],
    )

    train_in = TrainingInput(f"s3://{b}/{args.prefix}/train/", content_type="text/csv")
    val_in = TrainingInput(
        f"s3://{b}/{args.prefix}/validation/", content_type="text/csv"
    )

    try:
        # logs=True streams the job output into the console (Kiro Req 5.4).
        estimator.fit({"train": train_in, "validation": val_in}, logs=True)
    except Exception as exc:  # surface the real failure reason (Kiro Req 5.6)
        client = boto_sess.client("sagemaker")
        try:
            desc = client.describe_training_job(
                TrainingJobName=estimator.latest_training_job.name
            )
            print("TRAINING FAILED:", desc.get("FailureReason", str(exc)))
        except Exception:
            print("TRAINING FAILED:", exc)
        return 1

    print("model artifact:", estimator.model_data)  # Kiro Req 5.5
    return 0


if __name__ == "__main__":
    sys.exit(main())
