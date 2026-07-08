"""
Run a Data Wrangler `.flow` HEADLESSLY as a SageMaker Processing job — no UI import.

This is exactly what Data Wrangler's "Export -> Save to S3 (via processing job)"
generates: it spins up the managed **Data Wrangler processing container**, mounts
the `.flow` file, executes its transform graph, and writes the chosen output node
to S3. Same engine as the GUI, just driven from code.

NOTE on the flow file: `taxi.flow` in this folder is a hand-authored *scaffold*
(S3 source -> infer types -> drop missing). The launcher below is the correct,
standard mechanism, but a flow must be schema-valid to execute. For a guaranteed
run, point --flow at a real DW-exported flow, or validate the scaffold first
(`--dry-run` checks JSON + resolves the container image without spending).

Cost: one processing job on the DW container (~ml.m5.4xlarge, ~10-15 min ≈ a few
cents to ~$0.30). The same transforms also run for free headlessly via the Glue/
EMR/notebook scripts (shared/taxi_transforms.py) if you don't need the DW engine.

Usage:
    python run_flow_processing.py --bucket roi-smdemo-029331796573-us-east-1 \
        --role-arn arn:aws:iam::029331796573:role/roi-smdemo-exec-role \
        --profile roitraining --region us-east-1 --dry-run   # validate, no spend
    python run_flow_processing.py ... (drop --dry-run to actually run)
"""

import argparse
import json
import os
import sys

import boto3
import sagemaker
from sagemaker import image_uris
from sagemaker.processing import Processor, ProcessingInput, ProcessingOutput

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_FILE = os.path.join(HERE, "taxi.flow")


def output_node_name(flow_path: str) -> str:
    """The processing job emits one node's output: '<last_node_id>.default'."""
    with open(flow_path) as f:
        flow = json.load(f)
    last_node_id = flow["nodes"][-1]["node_id"]
    return f"{last_node_id}.default"


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument("--flow", default=FLOW_FILE)
    p.add_argument("--instance-type", default="ml.m5.4xlarge")  # DW default
    p.add_argument("--dry-run", action="store_true", help="validate without running")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm_sess = sagemaker.Session(boto_session=boto_sess)
    b = args.bucket

    # 1) Resolve the managed Data Wrangler container image for this region (the SDK
    #    knows the right per-region ECR account, so we don't hardcode it).
    image = image_uris.retrieve(framework="data-wrangler", region=args.region)
    output_name = output_node_name(args.flow)
    print(f"DW container image: {image}")
    print(f"output node:        {output_name}")

    if args.dry_run:
        print("dry-run OK: flow JSON parsed, output node resolved, image found. "
              "No processing job launched.")
        return 0

    # 2) Upload the flow file to S3 (the job mounts it at /opt/ml/processing/flow).
    flow_key = "dw/taxi.flow"
    boto_sess.client("s3").upload_file(args.flow, b, flow_key)
    flow_s3 = f"s3://{b}/{flow_key}"
    print(f"uploaded flow -> {flow_s3}")

    # 3) Build the processing job: flow as input, the output node to S3.
    processor = Processor(
        role=args.role_arn,
        image_uri=image,
        instance_count=1,
        instance_type=args.instance_type,
        volume_size_in_gb=30,
        sagemaker_session=sm_sess,
        base_job_name="roi-smdemo-dw-flow",
        tags=[{"Key": "Project", "Value": "sagemaker-unified-studio-demos"}],
    )

    flow_input = ProcessingInput(
        source=flow_s3,
        destination="/opt/ml/processing/flow",
        input_name="flow",
        s3_data_type="S3Prefix",
        s3_input_mode="File",
        s3_data_distribution_type="FullyReplicated",
    )
    output = ProcessingOutput(
        output_name=output_name,
        source="/opt/ml/processing/output",
        destination=f"s3://{b}/processed/data-wrangler/",
        s3_upload_mode="EndOfJob",
    )
    # The DW container reads which node to materialize from --output-config.
    output_config = {output_name: {"content_type": "CSV"}}

    processor.run(
        inputs=[flow_input],
        outputs=[output],
        arguments=["--output-config", json.dumps(output_config)],
        wait=True,
        logs=True,
    )
    print(f"done -> s3://{b}/processed/data-wrangler/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
