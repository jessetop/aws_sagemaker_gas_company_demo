"""
Module 6 — SageMaker Clarify: bias + explainability, the old way.

Runs a SageMaker Clarify processing job against the trained taxi model to compute
(a) pre-training bias metrics on a facet column and (b) SHAP feature-attribution
explainability. This is the classic SageMaker AI experience: configure a Clarify
processor and a few config objects in the SDK.

The NEW way surfaces the same bias/explainability reports inside the Unified Studio
model/asset view alongside training and lineage — see WALKTHROUGH.md.

Cost: one short processing job on the cheapest instance, then done.

Usage:
    python clarify_bias_explainability.py \
        --model-name roi-smdemo-taxi-model \
        --bucket roi-smdemo-029331796573-us-east-1 \
        --role-arn arn:aws:iam::029331796573:role/roi-smdemo-exec-role \
        --profile roitraining --region us-east-1
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker import clarify

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
    p.add_argument("--model-name", required=True, help="an existing SageMaker Model")
    add_common_args(p)
    p.add_argument("--prefix", default="ml/taxi")
    p.add_argument("--facet", default="is_airport_trip", help="bias facet column")
    p.add_argument(
        "--analysis-rows",
        type=int,
        default=300,
        help="rows sampled for Clarify (SHAP cost scales with this × num_samples)",
    )
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)
    b = args.bucket

    # IMPORTANT (cost): SHAP explainability evaluates the model ~num_samples times
    # PER ROW via an internal shadow endpoint. On the full 22.5k-row test set that
    # is millions of inferences (slow + costly). For a demo, run Clarify on a small
    # sample written here — a couple hundred rows is plenty to show a bias table and
    # SHAP feature ranking.
    s3 = boto_sess.client("s3")
    full = s3.get_object(Bucket=b, Key=f"{args.prefix}/test/test.csv")["Body"].read().decode()
    sample = "\n".join(full.splitlines()[: args.analysis_rows + 1]) + "\n"
    sample_key = "clarify-input/sample.csv"
    s3.put_object(Bucket=b, Key=sample_key, Body=sample)
    analysis_input = f"s3://{b}/{sample_key}"
    print(f"clarify analysis input: {analysis_input} ({args.analysis_rows} rows)")

    processor = clarify.SageMakerClarifyProcessor(
        role=args.role_arn,
        instance_count=1,
        instance_type="ml.m5.large",
        sagemaker_session=sm_sess,
    )

    # Bias and SHAP each write their own analysis.json/report.*. They MUST go to
    # separate prefixes — a shared output path means the second job overwrites the
    # first job's analysis.json (you'd lose the bias metrics). So: clarify/bias and
    # clarify/shap.
    headers = full.splitlines()[0].split(",")
    data_config_bias = clarify.DataConfig(
        s3_data_input_path=analysis_input,
        s3_output_path=f"s3://{b}/clarify/bias",
        label="high_tip",
        headers=headers,
        dataset_type="text/csv",
    )
    data_config_shap = clarify.DataConfig(
        s3_data_input_path=analysis_input,
        s3_output_path=f"s3://{b}/clarify/shap",
        label="high_tip",
        headers=headers,
        dataset_type="text/csv",
    )
    model_config = clarify.ModelConfig(
        model_name=args.model_name,
        instance_type="ml.m5.large",
        instance_count=1,
        accept_type="text/csv",
    )
    predictions_config = clarify.ModelPredictedLabelConfig(probability_threshold=0.5)
    bias_config = clarify.BiasConfig(
        label_values_or_threshold=[1],
        facet_name=args.facet,
    )

    # Bias (pre + post) and SHAP explainability — separate output prefixes.
    processor.run_bias(
        data_config=data_config_bias,
        bias_config=bias_config,
        model_config=model_config,
        model_predicted_label_config=predictions_config,
    )
    print("bias report:", f"s3://{b}/clarify/bias/")

    shap_config = clarify.SHAPConfig(num_samples=100, agg_method="mean_abs")
    processor.run_explainability(
        data_config=data_config_shap,
        model_config=model_config,
        explainability_config=shap_config,
    )
    print("explainability (SHAP) report:", f"s3://{b}/clarify/shap/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
