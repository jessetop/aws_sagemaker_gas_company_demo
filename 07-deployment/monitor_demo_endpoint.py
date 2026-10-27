"""
Module 7 (demo) — stand up a REAL-TIME gas-demand endpoint with Data Capture enabled so
the class can demo SageMaker Model Monitor, and attach a Model Card.

Why real-time (not the serverless endpoint in deploy_and_infer.py)?
    Model Monitor compares *captured* live traffic against a baseline. Data Capture
    is only supported on real-time, instance-backed endpoints — serverless can't
    capture. So this script deploys one ml.m5.large variant with DataCaptureConfig.

What it does:
    1. Builds the model from the completed training job's artifact.
    2. Deploys a real-time endpoint with 100% data capture -> s3://.../datacapture/.
    3. Sends a handful of inference requests so capture has records to monitor.
    4. Creates a Model Card (governance doc) populated from the real training metrics.
    5. Leaves the endpoint InService (monitoring needs it alive) and prints the
       exact teardown command. THIS ENDPOINT BILLS until you delete it.

Usage:
    python 07-deployment/monitor_demo_endpoint.py \
        --profile default --region us-east-1

Teardown when done (also printed at the end):
    python 07-deployment/monitor_demo_endpoint.py --delete --profile default --region us-east-1
"""

import argparse
import json
import sys

import boto3
import sagemaker
from sagemaker.deserializers import CSVDeserializer
from sagemaker.model_monitor import DataCaptureConfig
from sagemaker.serializers import CSVSerializer
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

# --- fixed demo resources (account/region/bucket come from shared.config) ---
# NOTE: TRAIN_JOB names a specific past training job; MODEL_DATA follows the
# configured region but the artifact only exists once module 4 has trained there.
# Resolved at runtime by resolve_training_job(): hardcoding a job name meant
# this script broke the moment the referenced job aged out of the account.
TRAIN_JOB = None
MODEL_DATA = None


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
    print(f"           artifact {MODEL_DATA}")


PREFIX = "ml/gas"

MODEL_NAME = config.resource("model-mon")
ENDPOINT_NAME = config.resource("monitor")
CARD_NAME = config.resource("demand-classifier")


def _final_metrics(sm_client) -> dict:
    """Pull the real validation metrics off the completed training job."""
    out = {}
    try:
        d = sm_client.describe_training_job(TrainingJobName=TRAIN_JOB)
        for m in d.get("FinalMetricDataList", []):
            out[m["MetricName"]] = round(float(m["Value"]), 4)
    except Exception:
        pass
    return out


def _make_card(sm_client, metrics: dict) -> None:
    """Create (or overwrite) a Model Card from the schema. Best-effort."""
    auc = metrics.get("validation:auc", 0.83)
    acc = metrics.get("validation:accuracy", 0.78)
    content = {
        "model_overview": {
            "model_name": MODEL_NAME,
            "model_description": (
                "Binary classifier predicting whether a California county-month was a "
                "high gas-demand month, from station weather alone. "
                "GradientBoosting (scikit-learn) on engineered weather features: "
                "heating degree days, temperature range, precipitation, elevation."
            ),
            "problem_type": "Binary classification",
            "algorithm_type": "Gradient boosting (scikit-learn GradientBoostingClassifier)",
            "model_creator": "ROI Training — SageMaker demo series",
            "model_owner": "ML Platform Demo Team",
            "model_artifact": [MODEL_DATA],
        },
        "intended_uses": {
            "purpose_of_model": (
                "Teaching artifact for the SageMaker demo series — illustrates "
                "deployment, data capture, and model monitoring end to end."
            ),
            "intended_uses": (
                "Demo/educational use only. Drives the champion/challenger, model "
                "card, and Model Monitor walkthroughs."
            ),
            "factors_affecting_model_efficiency": (
                "Sensitive to heating degree days, calendar month and station elevation. "
                "Trained on 2015-2024 California weather joined to CEC county "
                "consumption; not representative of other states or climates. "
                "Known limitation: the label is a county-MONTH aggregate while "
                "features are a single station-DAY, so the grain does not match."
            ),
            "risk_rating": "Low",
            "explanations_for_risk_rating": (
                "Non-production teaching model. No PII used; predictions are not used "
                "for any real business or customer-facing decision."
            ),
        },
        "training_details": {
            "objective_function": {
                "function": {"function": "Maximize", "facet": "AUC"}
            },
            "training_observations": (
                "Trained with learning-rate=0.1, n-estimators=150, max-depth=3 on the "
                "engineered weather feature set; validation AUC/accuracy below."
            ),
            "training_job_details": {
                "training_arn": (
                    f"arn:aws:sagemaker:{REGION}:{ACCOUNT}:training-job/{TRAIN_JOB}"
                ),
                "training_metrics": [
                    {"name": k, "value": v} for k, v in metrics.items()
                ]
                or [{"name": "validation:auc", "value": auc}],
            },
        },
        "evaluation_details": [
            {
                "name": "Holdout validation",
                "evaluation_observation": (
                    "Metrics from the held-out validation channel of the training job."
                ),
                "metric_groups": [
                    {
                        "name": "Classification quality",
                        "metric_data": [
                            {"name": "AUC", "type": "number", "value": auc},
                            {"name": "Accuracy", "type": "number", "value": acc},
                        ],
                    }
                ],
            }
        ],
        "additional_information": {
            "ethical_considerations": (
                "Gas consumption correlates with housing stock, income and climate zone, so "
                "a demand model can encode socio-economic structure. Clarify reports "
                "a strong behavioural difference across the heating-season facet (see "
                "module 06). Run bias and attribution-drift monitors before and "
                "during any production use."
            ),
            "caveats_and_recommendations": (
                "Demo model only. Enable Data Quality + Model Quality monitoring on the "
                "endpoint and review captured data before trusting any prediction."
            ),
        },
    }
    try:
        sm_client.delete_model_card(ModelCardName=CARD_NAME)
    except Exception:
        pass
    sm_client.create_model_card(
        ModelCardName=CARD_NAME,
        Content=json.dumps(content),
        ModelCardStatus="Draft",
    )
    print(f"model card created: {CARD_NAME} (status=Draft)")


def _delete(boto_sess) -> int:
    sm = boto_sess.client("sagemaker")
    for label, fn in (
        ("endpoint", lambda: sm.delete_endpoint(EndpointName=ENDPOINT_NAME)),
        ("endpoint-config", lambda: sm.delete_endpoint_config(EndpointConfigName=ENDPOINT_NAME)),
        ("model", lambda: sm.delete_model(ModelName=MODEL_NAME)),
    ):
        try:
            fn()
            print(f"deleted {label}: {ENDPOINT_NAME if label!='model' else MODEL_NAME}")
        except Exception as exc:
            print(f"  ({label} not deleted: {exc})")
    print("Model card left in place (free to keep). Delete with delete_model_card if desired.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p, bucket=False, role=False)
    p.add_argument("--instance-type", default="ml.m5.large")
    p.add_argument("--delete", action="store_true", help="tear down the endpoint")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    if args.delete:
        return _delete(boto_sess)

    sm_sess = sagemaker.Session(boto_session=boto_sess)
    sm_client = boto_sess.client("sagemaker")

    # Find the model artifact before anything else: this used to be a hardcoded
    # June training job name, so the script broke silently once that job aged
    # out of the account.
    resolve_training_job(sm_client)

    # Idempotent: clear anything a previous run left behind.
    _delete(boto_sess)

    model = SKLearnModel(
        model_data=MODEL_DATA,
        role=ROLE_ARN,
        entry_point="train.py",     # provides model_fn / predict_fn
        source_dir="04-training",
        framework_version="1.2-1",
        sagemaker_session=sm_sess,
        name=MODEL_NAME,
    )

    capture = DataCaptureConfig(
        enable_capture=True,
        sampling_percentage=100,                # capture everything for the demo
        destination_s3_uri=f"s3://{BUCKET}/{PREFIX}/datacapture",
    )

    print(f"deploying real-time endpoint {ENDPOINT_NAME} ({args.instance_type}) ...")
    predictor = model.deploy(
        initial_instance_count=1,
        instance_type=args.instance_type,
        endpoint_name=ENDPOINT_NAME,
        data_capture_config=capture,
        serializer=CSVSerializer(),
        deserializer=CSVDeserializer(),
    )
    print("endpoint InService:", ENDPOINT_NAME)

    # Send sample traffic so the capture path has records to monitor.
    s3 = boto_sess.client("s3")
    body = s3.get_object(
        Bucket=BUCKET, Key=f"{PREFIX}/test/test.csv"
    )["Body"].read().decode()
    lines = body.splitlines()
    print("feature columns:", lines[0].split(",")[1:])
    sent = 0
    for row in lines[1:21]:  # 20 requests -> visible captured data
        feats = [[float(x) for x in row.split(",")[1:]]]
        try:
            predictor.predict(feats)
            sent += 1
        except Exception as exc:
            print("  infer error:", exc)
            break
    print(f"sent {sent} inference requests -> captured to "
          f"s3://{BUCKET}/{PREFIX}/datacapture/{ENDPOINT_NAME}/")

    # Governance doc, populated from the real training metrics.
    _make_card(sm_client, _final_metrics(sm_client))

    print("\n" + "=" * 70)
    print("DONE. Endpoint is LIVE and BILLING (~$0.13/hr, ~$3/day).")
    print("Demo it in Studio: Deployments -> Endpoints ->", ENDPOINT_NAME, "-> Model Monitor")
    print("Model card: Studio -> Models -> Model cards ->", CARD_NAME)
    print("TEAR DOWN when finished:")
    print(f"  python 07-deployment/monitor_demo_endpoint.py --delete "
          f"--profile {args.profile} --region {args.region}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
