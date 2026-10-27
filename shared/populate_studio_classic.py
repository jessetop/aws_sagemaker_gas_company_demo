"""
Populate the Studio Classic panels that need specific SDK constructs:
  - **Experiments**: create an Experiment with one Run per training job (baseline +
    the 4 HPO trials), logging real hyperparameters and final metrics so the
    Experiments → compare view is populated (Kiro Req 4).
  - **Model Registry**: register the trained model into a model package group so the
    Model Registry panel shows a versioned, approved model.

Both are metadata operations — **no training compute** is launched. Run once to
make Studio Classic look complete for a class.

Usage:
    python populate_studio_classic.py --bucket roi-smdemo-029331796573-us-east-1 \
        --role-arn arn:aws:iam::029331796573:role/roi-smdemo-exec-role \
        --model-data s3://sagemaker-us-east-1-029331796573/<train-job>/output/model.tar.gz \
        --profile roitraining --region us-east-1
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker.experiments.run import Run
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

EXPERIMENT = config.resource("experiment")
MODEL_PACKAGE_GROUP = config.resource("models")


def _final_metrics(desc: dict) -> dict:
    """Pull {metric_name: value} from a training job description."""
    return {m["MetricName"]: m["Value"] for m in desc.get("FinalMetricDataList", [])}


def log_experiment(boto_sess, sm_sess) -> None:
    sm = boto_sess.client("sagemaker")

    # Gather the baseline job + the HPO trial jobs (all real training jobs).
    # NO MaxResults alongside NameContains: SageMaker applies the limit to the
    # page it fetches BEFORE the name filter, so MaxResults=1 returns nothing as
    # soon as the newest job in the account is not ours. Filter, then slice.
    jobs = []
    base = sm.list_training_jobs(
        NameContains=config.resource("train"), StatusEquals="Completed",
        SortBy="CreationTime", SortOrder="Descending",
    )["TrainingJobSummaries"]
    jobs += [j["TrainingJobName"] for j in base[:1]]
    hpo = sm.list_training_jobs(
        NameContains=config.resource("hpo"), StatusEquals="Completed",
        SortBy="CreationTime", SortOrder="Descending",
    )["TrainingJobSummaries"]
    jobs += [j["TrainingJobName"] for j in hpo[:10]]
    if not jobs:
        raise SystemExit(
            f"no Completed training jobs matching {config.resource('train')} or "
            f"{config.resource('hpo')}. Run 04-training then 05-experiments-tuning."
        )

    print(f"logging {len(jobs)} runs into experiment '{EXPERIMENT}'")
    for job in jobs:
        desc = sm.describe_training_job(TrainingJobName=job)
        hp = desc.get("HyperParameters", {})
        metrics = _final_metrics(desc)
        # Short, stable run name from the job suffix.
        run_name = job.replace(config.PREFIX + "-", "")[:60]
        with Run(
            experiment_name=EXPERIMENT, run_name=run_name, sagemaker_session=sm_sess
        ) as run:
            for k in ("learning-rate", "max-depth", "n-estimators"):
                if k in hp:
                    run.log_parameter(k, hp[k])
            for name, value in metrics.items():
                run.log_metric(name=name.replace(":", "_"), value=float(value))
        print(f"  logged run {run_name}  metrics={metrics}")


def register_model(args, sm_sess) -> None:
    model = SKLearnModel(
        model_data=args.model_data,
        role=args.role_arn,
        entry_point="train.py",
        source_dir="04-training",
        framework_version="1.2-1",
        sagemaker_session=sm_sess,
    )
    # register() creates a model package group + an approved version — metadata
    # only, no endpoint/compute.
    model.register(
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=["ml.m5.large", "ml.t2.medium"],
        transform_instances=["ml.m5.large"],
        model_package_group_name=MODEL_PACKAGE_GROUP,
        approval_status="Approved",
        description="GradientBoosting high_demand classifier (the gas utility gas-demand demo).",
    )
    print(f"registered model into package group '{MODEL_PACKAGE_GROUP}'")


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument(
        "--model-data",
        default=None,
        help="S3 model.tar.gz (default: newest Completed training job's artifact)",
    )
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)

    if not args.model_data:
        sm = boto_sess.client("sagemaker")
        found = sm.list_training_jobs(
            NameContains=config.resource("train"), StatusEquals="Completed",
            SortBy="CreationTime", SortOrder="Descending",
        )["TrainingJobSummaries"]
        if not found:
            raise SystemExit("no Completed training job to take a model artifact from")
        job = found[0]["TrainingJobName"]
        args.model_data = sm.describe_training_job(
            TrainingJobName=job
        )["ModelArtifacts"]["S3ModelArtifacts"]
        print(f"using artifact from {job}")

    log_experiment(boto_sess, sm_sess)
    register_model(args, sm_sess)
    print("done — Experiments and Model Registry are now populated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
