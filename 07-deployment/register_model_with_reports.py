"""
Module 7 (demo) — register the model into the Model Registry with the Clarify
bias + explainability reports attached, so the charts render NATIVELY in the console.

Why: running Clarify as a standalone processing job leaves the SHAP/bias charts as
HTML/JSON in S3 — the SageMaker console does NOT render them there. But if you attach
the reports' analysis.json files to a registered model *version* (via ModelMetrics),
Studio renders them under:
    Model registry -> <prefix>-models -> [version] -> Explainability  (SHAP)
    Model registry -> <prefix>-models -> [version] -> Bias            (bias metrics)

Prereq: the fixed clarify_bias_explainability.py has been run so BOTH reports exist:
    s3://<bucket>/clarify/bias/analysis.json
    s3://<bucket>/clarify/shap/analysis.json

Usage:
    python 07-deployment/register_model_with_reports.py \
        --profile default --region us-east-1
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker.model_metrics import MetricsSource, ModelMetrics
from sagemaker.sklearn.model import SKLearnModel

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args, ACCOUNT, REGION, BUCKET, ROLE_ARN

# Resolved at runtime by resolve_training_job(). These were pinned to a specific
# training job name, which meant the script broke silently the moment that job
# aged out of the account.
TRAIN_JOB = None
MODEL_DATA = None
GROUP = config.resource("models")


def resolve_training_job(sm_client) -> None:
    """Point TRAIN_JOB / MODEL_DATA at the newest Completed training job.

    No MaxResults alongside NameContains: SageMaker applies the limit to the
    page it fetches BEFORE the name filter, so MaxResults=1 silently returns
    nothing once an HPO trial is the newest job in the account.
    """
    global TRAIN_JOB, MODEL_DATA
    jobs = sm_client.list_training_jobs(
        NameContains=config.resource("train"), StatusEquals="Completed",
        SortBy="CreationTime", SortOrder="Descending",
    )["TrainingJobSummaries"]
    if not jobs:
        raise SystemExit(
            f"no Completed training job matching {config.resource('train')}. "
            f"Run 04-training/launch_training.py first."
        )
    TRAIN_JOB = jobs[0]["TrainingJobName"]
    MODEL_DATA = sm_client.describe_training_job(
        TrainingJobName=TRAIN_JOB
    )["ModelArtifacts"]["S3ModelArtifacts"]
    print(f"using training job {TRAIN_JOB}")


def _exists(s3, key: str) -> bool:
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except Exception:
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p, bucket=False, role=False)
    p.add_argument("--bias-key", default="clarify/bias/analysis.json")
    p.add_argument("--shap-key", default="clarify/shap/analysis.json")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)
    s3 = boto_sess.client("s3")

    # Find the model artifact first: this used to be a pinned job name, so the
    # script broke silently once that job aged out of the account.
    resolve_training_job(boto_sess.client("sagemaker"))

    # Both reports must exist or the corresponding console tab will be empty.
    for label, key in (("bias", args.bias_key), ("explainability", args.shap_key)):
        if not _exists(s3, key):
            print(f"ERROR: {label} report not found at s3://{BUCKET}/{key}")
            print("Run 06-clarify-debugger-groundtruth/clarify_bias_explainability.py first.")
            return 1

    bias_uri = f"s3://{BUCKET}/{args.bias_key}"
    shap_uri = f"s3://{BUCKET}/{args.shap_key}"

    # The reports attach to the model version through ModelMetrics. The bias
    # analysis.json contains BOTH pre- and post-training metrics, so we point the
    # pre/post slots at the same file; the console Bias tab reads from it.
    model_metrics = ModelMetrics(
        bias_pre_training=MetricsSource(s3_uri=bias_uri, content_type="application/json"),
        bias_post_training=MetricsSource(s3_uri=bias_uri, content_type="application/json"),
        explainability=MetricsSource(s3_uri=shap_uri, content_type="application/json"),
    )

    model = SKLearnModel(
        model_data=MODEL_DATA,
        role=ROLE_ARN,
        entry_point="train.py",
        source_dir="04-training",
        framework_version="1.2-1",
        sagemaker_session=sm_sess,
    )

    print(f"registering a new version into {GROUP} with bias + explainability attached ...")
    model_package = model.register(
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=["ml.m5.large"],
        transform_instances=["ml.m5.large"],
        model_package_group_name=GROUP,
        approval_status="Approved",
        model_metrics=model_metrics,
        description="Gas-demand classifier with Clarify bias + SHAP reports attached.",
    )

    arn = model_package.model_package_arn
    version = arn.rsplit("/", 1)[-1]
    print(f"registered: {arn}")
    print(f"\nIn Studio -> Model registry -> {GROUP} -> version {version}:")
    print("  • Explainability tab  (SHAP feature attributions)")
    print("  • Bias tab            (pre/post-training bias metrics)")
    print(f"  bias report: {bias_uri}")
    print(f"  shap report: {shap_uri}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
