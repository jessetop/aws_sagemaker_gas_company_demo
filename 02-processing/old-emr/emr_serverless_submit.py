"""
Module 2 (old way) — submit the taxi pipeline to EMR Serverless.

This is the "do it yourself" path a data engineer uses outside any studio: create
a serverless Spark application, ship the code to S3, submit a Spark job, and tail
the logs. It's cheap (pay only for the vCPU/memory-seconds the job uses) and needs
no running cluster — but YOU wire up the app, the submit call, the role, and the
log location. The new way (Module 2 notebook) does the same Spark work from a
managed Unified Studio notebook with none of this plumbing.

Usage:
    python emr_serverless_submit.py \
        --bucket roi-smdemo-029331796573-us-east-1 \
        --role-arn arn:aws:iam::029331796573:role/roi-smdemo-exec-role \
        --profile roitraining --region us-east-1
"""

import argparse
import sys
import time

import boto3

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args


def get_or_create_app(emr, name: str) -> str:
    """Reuse an existing demo application by name, else create one."""
    for app in emr.list_applications().get("applications", []):
        if app["name"] == name:
            return app["id"]
    resp = emr.create_application(
        name=name,
        releaseLabel="emr-7.1.0",
        type="SPARK",
        # Auto-stop so we never pay for an idle application.
        autoStopConfiguration={"enabled": True, "idleTimeoutMinutes": 5},
        tags={"Project": "sagemaker-unified-studio-demos", "ManagedBy": "demo"},
    )
    return resp["applicationId"]


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    args = p.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    emr = session.client("emr-serverless")
    b = args.bucket

    app_id = get_or_create_app(emr, "roi-smdemo-taxi-emr")
    print(f"application: {app_id}")

    # Submit the Spark job. entryPoint is our script in S3; --py-files ships the
    # shared transforms module so `from taxi_transforms import ...` resolves.
    run = emr.start_job_run(
        applicationId=app_id,
        executionRoleArn=args.role_arn,
        name="taxi-pipeline",
        jobDriver={
            "sparkSubmit": {
                "entryPoint": f"s3://{b}/code/emr_taxi_job.py",
                "entryPointArguments": [
                    f"s3://{b}/raw/trips/",
                    f"s3://{b}/raw/zones/taxi_zone_lookup.csv",
                    f"s3://{b}/processed/emr/",
                ],
                "sparkSubmitParameters": (
                    f"--py-files s3://{b}/code/taxi_transforms.py "
                    "--conf spark.executor.cores=2 --conf spark.executor.memory=4g"
                ),
            }
        },
        configurationOverrides={
            "monitoringConfiguration": {
                "s3MonitoringConfiguration": {"logUri": f"s3://{b}/logs/emr/"}
            }
        },
    )
    job_id = run["jobRunId"]
    print(f"job run: {job_id}")

    # Poll to completion so the demo shows the full lifecycle.
    terminal = {"SUCCESS", "FAILED", "CANCELLED"}
    while True:
        jr = emr.get_job_run(applicationId=app_id, jobRunId=job_id)["jobRun"]
        print(f"  state={jr['state']} {jr.get('stateDetails','')}")
        if jr["state"] in terminal:
            break
        time.sleep(20)

    return 0 if jr["state"] == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
