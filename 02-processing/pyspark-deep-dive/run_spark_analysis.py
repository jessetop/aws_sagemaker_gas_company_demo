"""
Run the PySpark deep dive as a Glue job -- the cheap way to PROVE the notebook.

No EMR cluster is created. Nothing is left running. Glue bills per second with
a one-minute minimum, so a full run of this analysis costs roughly $0.30 and
then stops existing.

Why a Glue job rather than an interactive session for verification: a job has a
terminal state and a log you can read afterwards, so "did every cell work?" has
a yes/no answer. Interactive sessions are the right tool for *teaching* (see
NOTEBOOK.md) but a bad tool for CI-style verification.

Usage:
    python 02-processing/pyspark-deep-dive/run_spark_analysis.py --start
    python 02-processing/pyspark-deep-dive/run_spark_analysis.py --logs
"""

import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args

SCRIPT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "gas_spark_analysis.py")
DONE = {"SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"}


def main() -> int:
    p = argparse.ArgumentParser(description="Run the PySpark deep dive on Glue.")
    add_common_args(p)
    p.add_argument("--start", action="store_true", help="Start the job and wait")
    p.add_argument("--logs", action="store_true", help="Show the last run's status")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    job_name = config.resource("spark-deep-dive")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    glue = session.client("glue")
    s3 = session.client("s3")
    b = args.bucket

    if args.logs:
        runs = glue.get_job_runs(JobName=job_name, MaxResults=1).get("JobRuns", [])
        if not runs:
            print(f"no runs for {job_name}")
            return 1
        r = runs[0]
        print(f"run {r['Id']}: {r['JobRunState']}  ({r.get('ExecutionTime')}s)")
        if r.get("ErrorMessage"):
            print(f"  ERROR: {r['ErrorMessage']}")
        print(f"  driver log: /aws-glue/jobs/output  stream {r['Id']}")
        return 0 if r["JobRunState"] == "SUCCEEDED" else 1

    key = "code/gas_spark_analysis.py"
    print(f"uploading analysis -> s3://{b}/{key}")
    s3.upload_file(SCRIPT, b, key)

    job_def = dict(
        Role=args.role_arn,
        GlueVersion="4.0",
        NumberOfWorkers=args.workers,
        WorkerType="G.1X",
        Timeout=45,
        Command={
            "Name": "glueetl",
            "ScriptLocation": f"s3://{b}/{key}",
            "PythonVersion": "3",
        },
        DefaultArguments={
            "--job-language": "python",
            "--TempDir": f"s3://{b}/tmp/glue/",
            "--enable-continuous-cloudwatch-log": "true",
            "--bucket": b,
        },
        Tags={"Project": "sagemaker-unified-studio-demos"},
    )
    try:
        glue.create_job(Name=job_name, **job_def)
        print(f"created job '{job_name}'")
    except glue.exceptions.AlreadyExistsException:
        glue.update_job(JobName=job_name, JobUpdate={k: v for k, v in job_def.items() if k != "Tags"})
        print(f"updated job '{job_name}'")

    if not args.start:
        print("pass --start to run it")
        return 0

    run_id = glue.start_job_run(JobName=job_name)["JobRunId"]
    print(f"run id: {run_id}")
    last, started = None, time.time()
    while True:
        try:
            run = glue.get_job_run(JobName=job_name, RunId=run_id)["JobRun"]
        except ClientError as exc:
            print(f"  (transient) {exc}")
            time.sleep(15)
            continue
        state = run["JobRunState"]
        if state != last:
            print(f"  [{time.time() - started:6.0f}s] {state}")
            last = state
        if state in DONE:
            break
        time.sleep(20)

    print(f"\nfinal: {state}  ({run.get('ExecutionTime')}s)")
    dpu = run.get("DPUSeconds")
    if dpu:
        print(f"DPU-hours: {dpu/3600:.4f}  (~${dpu/3600*0.44:.4f})")
    if run.get("ErrorMessage"):
        print(f"ERROR: {run['ErrorMessage']}")
    if state != "SUCCEEDED":
        print(f"\nDriver log: aws logs tail /aws-glue/jobs/error "
              f"--log-stream-names {run_id} --profile {args.profile} --region {args.region}")
        return 1
    print(f"\nRead the analysis output:")
    print(f"  aws logs get-log-events --log-group-name /aws-glue/jobs/output \\")
    print(f"    --log-stream-name {run_id} --profile {args.profile} --region {args.region} \\")
    print(f"    --query 'events[].message' --output text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
