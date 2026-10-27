"""
Create a real **Visual ETL** flow (visual-node Glue job) so it renders on the
Unified Studio / Glue Studio canvas — the thing to compare against Data Wrangler.

Our other Glue job (the one run by run_glue_job.py) is a *script* job, so it does NOT
appear in the visual editor. A visual flow needs `CodeGenConfigurationNodes` — the
JSON DAG the canvas reads. This builds a simple, recognizable flow:

    S3 source (GHCN observations) -> Drop Duplicates -> Drop Fields -> S3 target

It's tagged to the Unified Studio project so it shows up there, and it's
deliberately simple ("drop dupes, drop fields") to mirror common Data Wrangler
transforms for the side-by-side.

Usage:
    python create_visual_flow.py --bucket YOUR-BUCKET-NAME \
        --role-arn arn:aws:iam::000000000000:role/roi-smdemo-exec-role \
        --profile default --region us-east-1
"""

import argparse
import sys

import boto3

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args

JOB_NAME = config.resource("visual-flow")
# Tag to the user's Unified Studio project (Default_06222026_Domain).
DZ_TAGS = {
    "AmazonDataZoneProject": "azjpw3giqinpux",
    "AmazonDataZoneDomain": "dzd-6jlg4btaz2tp49",
    "AmazonDataZoneEnvironment": "cuv9xh4sdcppyh",
    "Project": "sagemaker-unified-studio-demos",
}


def build_nodes(bucket: str) -> dict:
    """The visual DAG the canvas renders. Node IDs are arbitrary unique strings."""
    src, dedup, drop, tgt = "node_source", "node_dropdup", "node_dropfields", "node_target"
    return {
        src: {
            "S3ParquetSource": {
                "Name": "GHCN Observations",
                "Paths": [f"s3://{bucket}/raw/trips/"],
                "Recurse": True,
            }
        },
        dedup: {
            # Data Wrangler's "Drop duplicates" <-> this visual node.
            "DropDuplicates": {"Name": "Drop Duplicate Trips", "Inputs": [src]}
        },
        drop: {
            # Data Wrangler's "Manage columns -> Drop" <-> this visual node.
            "DropFields": {
                "Name": "Drop Unused Fields",
                "Inputs": [dedup],
                "Paths": [["store_and_fwd_flag"], ["mta_tax"], ["improvement_surcharge"]],
            }
        },
        tgt: {
            "S3GlueParquetTarget": {
                "Name": "Cleaned Trips",
                "Inputs": [drop],
                "Path": f"s3://{bucket}/processed/visual-demo/",
                "Compression": "snappy",
            }
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    args = p.parse_args()

    glue = boto3.Session(profile_name=args.profile, region_name=args.region).client("glue")
    b = args.bucket

    job_args = dict(
        Name=JOB_NAME,
        Role=args.role_arn,
        GlueVersion="4.0",
        NumberOfWorkers=2,
        WorkerType="G.1X",
        Command={
            "Name": "glueetl",
            # Glue stores/generates the script here from the visual nodes.
            "ScriptLocation": f"s3://{b}/code/visual_flow_generated.py",
            "PythonVersion": "3",
        },
        DefaultArguments={"--job-language": "python", "--TempDir": f"s3://{b}/tmp/glue/"},
        CodeGenConfigurationNodes=build_nodes(b),
        Tags=DZ_TAGS,
    )
    try:
        glue.create_job(**job_args)
        print(f"created visual flow job '{JOB_NAME}'")
    except glue.exceptions.IdempotentParameterMismatchException:
        glue.update_job(JobName=JOB_NAME, JobUpdate={k: v for k, v in job_args.items() if k != "Name"})
        print(f"updated visual flow job '{JOB_NAME}'")
    except glue.exceptions.AlreadyExistsException:
        upd = {k: v for k, v in job_args.items() if k not in ("Name", "Tags")}
        glue.update_job(JobName=JOB_NAME, JobUpdate=upd)
        print(f"updated existing visual flow job '{JOB_NAME}'")

    print("Open it in Unified Studio -> Build -> Visual ETL (or Glue Studio -> Visual).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
