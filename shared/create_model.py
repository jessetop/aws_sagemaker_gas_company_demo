"""
Create the SageMaker **Model** object from the latest completed training job.

Why this exists as its own step: Clarify needs a Model to run against. It spins
up a shadow endpoint from the Model to get predictions for SHAP and
post-training bias metrics, so `--model-name` is required and the prebake run
fails at argparse without it.

The two existing scripts that create a Model both do more than we want here:

  - 07-deployment/deploy_and_infer.py creates a Model AND deploys an endpoint,
    which bills by the hour.
  - 07-deployment/register_model_with_reports.py also registers a model package
    into the registry, which is a separate demo.

Creating a Model on its own is **free** -- it is just metadata pointing at the
model artifact in S3. Nothing runs until something invokes it. So this is the
right prerequisite for Clarify, and it also populates the "Models" panel in the
console, which is worth pointing at during the training demo.

Usage:
    python shared/create_model.py
    python shared/create_model.py --training-job roi-smdemo-gas-train-...
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker.sklearn.model import SKLearnModel

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args

# train.py doubles as the inference entry point (model_fn / predict_fn).
ENTRY_POINT = _os.path.join(_root, "04-training", "train.py")


def latest_training_job(sm, name_contains: str) -> str:
    """Newest Completed training job whose name contains `name_contains`.

    NOTE: no MaxResults here, deliberately. SageMaker applies MaxResults to the
    page it fetches BEFORE applying NameContains, so `MaxResults=1` plus a name
    filter returns zero whenever the single newest job in the account happens
    not to match -- which is exactly what happens once HPO trial jobs exist.
    Filter first, then take the newest.
    """
    jobs = sm.list_training_jobs(
        NameContains=name_contains,
        StatusEquals="Completed",
        SortBy="CreationTime",
        SortOrder="Descending",
    )["TrainingJobSummaries"]
    if not jobs:
        raise RuntimeError(
            f"no Completed training job containing '{name_contains}'. "
            f"Run 04-training/launch_training.py first."
        )
    return jobs[0]["TrainingJobName"]


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create the SageMaker Model object (free; no endpoint)."
    )
    add_common_args(p)
    p.add_argument(
        "--training-job",
        default=None,
        help="Training job to take the artifact from (default: newest Completed)",
    )
    args = p.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm = session.client("sagemaker")
    sm_session = sagemaker.Session(boto_session=session)

    job = args.training_job or latest_training_job(sm, config.resource("train"))
    desc = sm.describe_training_job(TrainingJobName=job)
    model_data = desc["ModelArtifacts"]["S3ModelArtifacts"]
    metrics = {m["MetricName"]: m["Value"] for m in desc.get("FinalMetricDataList", [])}
    print(f"training job : {job}")
    print(f"artifact     : {model_data}")
    print(f"metrics      : {metrics}")

    model_name = config.resource("model")

    # Idempotent: delete an existing Model of the same name so re-running the
    # prebake does not fail on a name clash. Deleting a Model does not touch the
    # artifact in S3, and it cannot affect a running endpoint (the endpoint
    # holds its own copy of the config).
    try:
        sm.describe_model(ModelName=model_name)
        print(f"replacing existing model '{model_name}'")
        sm.delete_model(ModelName=model_name)
    except sm.exceptions.ClientError:
        pass

    model = SKLearnModel(
        model_data=model_data,
        role=args.role_arn,
        entry_point=ENTRY_POINT,
        framework_version="1.2-1",
        sagemaker_session=sm_session,
        name=model_name,
    )
    # create() rather than deploy(): registers the Model and nothing else.
    model.create(instance_type="ml.m5.large")
    print(f"\ncreated model '{model_name}'")
    print("Clarify can now run against it:")
    print(f"  python 06-clarify-debugger-groundtruth/clarify_bias_explainability.py "
          f"--model-name {model_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
