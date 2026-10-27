"""
Module 9 — SageMaker Autopilot (AutoML) on the gas-demand dataset.

Runs a COST-CAPPED Autopilot job that produces a ranked candidate leaderboard for
predicting `high_demand` — the "model ranking" demo. Autopilot is the one demo that
costs dollars (not cents) because it trains many models, so this script constrains
it hard: a small data sample, ENSEMBLING mode, max 10 candidates, and runtime caps.

Old way: SageMaker Autopilot (here / Studio Classic leaderboard UI).
New way: the same AutoML via SageMaker Canvas inside Unified Studio (no-code).

Rough cost with defaults below: ~$2-6, ~40-75 min. Unconstrained Autopilot can be
$20-50+ over several hours — DON'T remove the caps for a class.

Usage:
    python launch_autopilot.py --bucket YOUR-BUCKET-NAME \
        --role-arn arn:aws:iam::000000000000:role/roi-smdemo-exec-role \
        --profile default --region us-east-1          # launch (no wait)
    python launch_autopilot.py ... --leaderboard           # print ranking of a done job
"""

import argparse
import io
import sys

import boto3
import pandas as pd
import sagemaker
from sagemaker.automl.automlv2 import (
    AutoMLV2,
    AutoMLTabularConfig,
    AutoMLDataChannel,
)

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args

JOB_NAME = config.resource("autopilot")
# Tag with the LIVE us-east-1 Unified Studio domain so the job is discoverable
# there. Project/Environment are optional and only needed to pin it to a specific
# US project — set SMDEMO_DZ_PROJECT / SMDEMO_DZ_ENVIRONMENT to enable. The job
# always shows in SageMaker AI Studio's Autopilot view regardless of these tags.
DZ_TAGS = [{"Key": "AmazonDataZoneDomain", "Value": _os.environ.get("SMDEMO_DZ_DOMAIN", "dzd-b6xs075popdjhj")}]
if _os.environ.get("SMDEMO_DZ_PROJECT"):
    DZ_TAGS.append({"Key": "AmazonDataZoneProject", "Value": _os.environ["SMDEMO_DZ_PROJECT"]})
if _os.environ.get("SMDEMO_DZ_ENVIRONMENT"):
    DZ_TAGS.append({"Key": "AmazonDataZoneEnvironment", "Value": _os.environ["SMDEMO_DZ_ENVIRONMENT"]})


def print_leaderboard(sm, job_name: str) -> None:
    """Show the ranked candidates (the model-ranking payoff)."""
    desc = sm.describe_auto_ml_job_v2(AutoMLJobName=job_name)
    print("status:", desc["AutoMLJobStatus"], desc.get("AutoMLJobSecondaryStatus", ""))
    cands = sm.list_candidates_for_auto_ml_job(
        AutoMLJobName=job_name, SortBy="FinalObjectiveMetricValue", SortOrder="Descending"
    )["Candidates"]
    print(f"\n{'rank':<5}{'candidate':<45}{'metric':<10}value")
    for i, c in enumerate(cands, 1):
        m = c.get("FinalAutoMLJobObjectiveMetric", {})
        print(f"{i:<5}{c['CandidateName'][:44]:<45}{m.get('MetricName',''):<10}{m.get('Value','')}")


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument("--sample-rows", type=int, default=15000)
    p.add_argument("--max-candidates", type=int, default=10)
    p.add_argument("--leaderboard", action="store_true", help="just print the ranking")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm = boto_sess.client("sagemaker")
    if args.leaderboard:
        print_leaderboard(sm, JOB_NAME)
        return 0

    sm_sess = sagemaker.Session(boto_session=boto_sess)
    b = args.bucket

    # Build a small sample so each candidate trains fast (cost control).
    s3 = boto_sess.client("s3")
    full = s3.get_object(Bucket=b, Key="ml/gas/train/train.csv")["Body"].read()
    df = pd.read_csv(io.BytesIO(full)).head(args.sample_rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    s3.put_object(Bucket=b, Key="ml/gas/autopilot/train.csv", Body=buf.getvalue())
    input_path = f"s3://{b}/ml/gas/autopilot/train.csv"
    print(f"autopilot input: {input_path} ({len(df)} rows)")

    automl = AutoMLV2(
        problem_config=AutoMLTabularConfig(
            target_attribute_name="high_demand",
            problem_type="BinaryClassification",
            max_candidates=args.max_candidates,          # cost cap
            max_runtime_per_training_job_in_seconds=600,  # cost cap
            max_total_job_runtime_in_seconds=3600,        # cost cap (1h)
            mode="ENSEMBLING",                            # cheaper than HPO
        ),
        base_job_name=JOB_NAME,
        output_path=f"s3://{b}/autopilot-output/",
        role=args.role_arn,
        sagemaker_session=sm_sess,
        job_objective={"MetricName": "Accuracy"},
        tags=DZ_TAGS,
    )
    # AutoMLV2 wants a structured data channel, not a bare S3 string.
    channel = AutoMLDataChannel(
        s3_data_type="S3Prefix", s3_uri=input_path, channel_type="training"
    )
    # wait=False so this returns immediately; poll with --leaderboard later.
    automl.fit(inputs=[channel], wait=False, job_name=JOB_NAME)
    print(f"launched Autopilot job '{JOB_NAME}' (max {args.max_candidates} candidates,"
          f" ENSEMBLING). Check the leaderboard with --leaderboard or in Studio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
