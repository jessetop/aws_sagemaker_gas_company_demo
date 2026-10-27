"""
Module 6B — SageMaker Debugger with REAL captured data (old way).

The custom sklearn model (train.py) can't emit Debugger tensors — Debugger only
natively hooks XGBoost / PyTorch / TF / MXNet. So the Debugger demo trains the
SAME task (predict `high_demand`) on the SAME data with **built-in XGBoost**, which
auto-captures tensors with zero instrumentation. You get:

  * a real training/validation **loss curve** (metrics collection, per round)
  * **feature_importance** + **average_shap** collections
  * built-in **rules** evaluated live: LossNotDecreasing, Overfit

Open the training job in SageMaker AI Studio -> "Debugger" to see the charts +
rule outcomes. NEW way: Unified Studio surfaces the same profiling/insight in the
project training view.

Data: the pipeline already wrote label-first, headerless CSVs (XGBoost's required
format) to s3://<bucket>/pipeline/train|validation/.

Usage:
    python 06-clarify-debugger-groundtruth/launch_debugger_xgboost.py
    python .../launch_debugger_xgboost.py --num-round 80 --prefix pipeline
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker import image_uris
from sagemaker.debugger import CollectionConfig, DebuggerHookConfig, Rule, rule_configs
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument("--instance-type", default="ml.m5.large")
    p.add_argument("--prefix", default="pipeline", help="holds train/ and validation/ CSVs")
    p.add_argument("--num-round", type=int, default=60, help="boosting rounds (loss-curve length)")
    p.add_argument("--wait", action="store_true", help="stream logs + block until done")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)
    b = args.bucket

    # Built-in XGBoost algorithm image (natively supported by Debugger).
    xgb_image = image_uris.retrieve("xgboost", args.region, version="1.7-1")

    # Capture the collections that render as charts in the Debugger tab.
    hook_config = DebuggerHookConfig(
        s3_output_path=f"s3://{b}/debugger/xgboost",
        collection_configs=[
            CollectionConfig(name="metrics", parameters={"save_interval": "1"}),
            CollectionConfig(name="feature_importance", parameters={"save_interval": "1"}),
            CollectionConfig(name="average_shap", parameters={"save_interval": "1"}),
        ],
    )

    # Built-in rules evaluate common pathologies in parallel, for free.
    rules = [
        Rule.sagemaker(rule_configs.loss_not_decreasing()),
        Rule.sagemaker(rule_configs.overfit()),
    ]

    estimator = Estimator(
        image_uri=xgb_image,
        role=args.role_arn,
        instance_count=1,
        instance_type=args.instance_type,
        sagemaker_session=sm_sess,
        base_job_name=config.resource("debugger"),
        hyperparameters={
            "objective": "binary:logistic",
            "num_round": str(args.num_round),
            "max_depth": "5",
            "eta": "0.2",
            "subsample": "0.8",
            # logloss drives the loss curve; auc is the familiar quality metric.
            "eval_metric": "logloss,auc",
        },
        debugger_hook_config=hook_config,
        rules=rules,
        tags=[{"Key": "Project", "Value": "sagemaker-unified-studio-demos"}],
    )

    # XGBoost built-in wants label-first, headerless CSV — which is exactly what
    # the pipeline's preprocess step wrote.
    inputs = {
        "train": TrainingInput(f"s3://{b}/{args.prefix}/train/", content_type="csv"),
        "validation": TrainingInput(f"s3://{b}/{args.prefix}/validation/", content_type="csv"),
    }

    estimator.fit(inputs, logs=args.wait, wait=args.wait)
    job = estimator.latest_training_job.name
    print(f"training job: {job}")

    if args.wait:
        print("\nDebugger rule outcomes:")
        for s in estimator.latest_training_job.rule_job_summary():
            print(f"  {s['RuleConfigurationName']:<28} {s['RuleEvaluationStatus']}")
    else:
        print("started (async). Watch it in SageMaker AI Studio -> Training -> "
              f"{job} -> Debugger tab.")
    print(f"debugger tensors: s3://{b}/debugger/xgboost")
    return 0


if __name__ == "__main__":
    sys.exit(main())
