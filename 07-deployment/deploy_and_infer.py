"""
Module 7 — deploy the trained model and run inference (Kiro Req 7), old way.

Uses the cheapest serving option — **Serverless Inference** — so there is no
always-on instance to forget about. Deploys the model from a completed training
job, sends a few inference requests, prints predictions, then DELETES the endpoint
(Kiro Req 7.4) so nothing keeps billing.

The NEW way deploys the same model from a Unified Studio project (governed,
one-click) — see WALKTHROUGH.md.

Usage:
    python deploy_and_infer.py \
        --model-data s3://.../model.tar.gz \
        --role-arn arn:aws:iam::000000000000:role/roi-smdemo-exec-role \
        --bucket YOUR-BUCKET-NAME \
        --profile default --region us-east-1
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker.deserializers import CSVDeserializer
from sagemaker.serializers import CSVSerializer
from sagemaker.serverless import ServerlessInferenceConfig
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


def newest_model_artifact(sm) -> str:
    """S3 artifact of the newest Completed training job for this series.

    No MaxResults alongside NameContains: SageMaker applies the limit to the
    page it fetches BEFORE the name filter, so MaxResults=1 silently returns
    nothing once an HPO trial is the newest job in the account.
    """
    jobs = sm.list_training_jobs(
        NameContains=config.resource("train"), StatusEquals="Completed",
        SortBy="CreationTime", SortOrder="Descending",
    )["TrainingJobSummaries"]
    if not jobs:
        raise SystemExit(
            f"no Completed training job matching {config.resource('train')}. "
            f"Run 04-training/launch_training.py first."
        )
    job = jobs[0]["TrainingJobName"]
    uri = sm.describe_training_job(TrainingJobName=job)["ModelArtifacts"]["S3ModelArtifacts"]
    print(f"using artifact from {job}")
    return uri


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model-data", default=None,
                   help="s3:// path to model.tar.gz "
                        "(default: newest Completed training job)")
    add_common_args(p)
    p.add_argument("--prefix", default="ml/gas")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)

    if not args.model_data:

        args.model_data = newest_model_artifact(boto_sess.client("sagemaker"))
    sm_sess = sagemaker.Session(boto_session=boto_sess)

    # Idempotent: drop a model / endpoint-config left by a previous run.
    _sm = boto_sess.client("sagemaker")
    for _del in (
        lambda: _sm.delete_model(ModelName=config.resource("model")),
        lambda: _sm.delete_endpoint_config(EndpointConfigName=config.resource("endpoint")),
    ):
        try:
            _del()
        except Exception:
            pass

    model = SKLearnModel(
        model_data=args.model_data,
        role=args.role_arn,
        entry_point="train.py",          # provides model_fn / predict_fn
        source_dir="04-training",
        framework_version="1.2-1",
        sagemaker_session=sm_sess,
        name=config.resource("model"),
    )

    endpoint_name = config.resource("endpoint")
    predictor = None
    try:
        # Serverless: scales to zero, pay per request + duration. Cheapest demo.
        # CSV in / CSV out so we can send a plain feature row and read a number.
        predictor = model.deploy(
            serverless_inference_config=ServerlessInferenceConfig(
                memory_size_in_mb=2048, max_concurrency=2
            ),
            endpoint_name=endpoint_name,
            serializer=CSVSerializer(),
            deserializer=CSVDeserializer(),
        )
        print("endpoint InService:", endpoint_name)

        # Pull 3 sample rows from the held-out test set (features only) and score.
        s3 = boto_sess.client("s3")
        body = s3.get_object(
            Bucket=args.bucket, Key=f"{args.prefix}/test/test.csv"
        )["Body"].read().decode()
        lines = body.splitlines()
        header = lines[0].split(",")
        print("feature columns:", header[1:])
        for row in lines[1:4]:  # 3 inference requests (Kiro Req 7.3)
            # Drop the label column; send the numeric feature row as one CSV line.
            feats = [[float(x) for x in row.split(",")[1:]]]
            pred = predictor.predict(feats)
            print(f"  P(high_demand) = {pred}")
    except Exception as exc:
        print("DEPLOY/INFER ERROR:", exc)
        return 1
    finally:
        # Always tear the endpoint down (Kiro Req 7.4).
        if predictor is not None:
            predictor.delete_endpoint()
            print("deleted endpoint:", endpoint_name)
        else:
            try:
                boto_sess.client("sagemaker").delete_endpoint(
                    EndpointName=endpoint_name
                )
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
