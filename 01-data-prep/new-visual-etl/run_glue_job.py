"""
Create and run the Visual-ETL-equivalent Glue job (Module 1, the "new way").

The taxi version of this series created its Glue job ad hoc, which meant the
one command that proves the pipeline works was not in the repo. This script is
that missing piece: it uploads the job script plus the shared transform module,
creates or updates the Glue job, optionally starts it, and tails the run to a
terminal state so a failure is visible rather than silent.

Cost: 2 x G.1X workers for a few minutes — cents. Glue bills per second with a
1-minute minimum, so there is nothing left running after the job finishes.

Usage:
    python run_glue_job.py                  # create/update the job only
    python run_glue_job.py --start          # ...and run it, waiting for the result
    python run_glue_job.py --start --workers 4
    python run_glue_job.py --logs           # print the last run's error, if any
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

JOB_SCRIPT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "glue_visual_etl_job.py")
TRANSFORMS = _os.path.join(_root, "shared", "gas_transforms.py")

# Terminal run states, per the Glue API.
DONE = {"SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"}


def upload(s3, bucket: str, local: str, key: str) -> str:
    print(f"  uploading {_os.path.basename(local)} -> s3://{bucket}/{key}")
    s3.upload_file(local, bucket, key)
    return f"s3://{bucket}/{key}"


def main() -> int:
    p = argparse.ArgumentParser(description="Create + run the Module 1 Glue job.")
    add_common_args(p)
    p.add_argument("--start", action="store_true", help="Start the job and wait for it")
    p.add_argument("--logs", action="store_true", help="Show the last run's status/error and exit")
    p.add_argument("--workers", type=int, default=2, help="G.1X worker count (default 2)")
    p.add_argument("--timeout-min", type=int, default=30, help="Glue job timeout, minutes")
    args = p.parse_args()

    job_name = config.resource("visual-etl")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    glue = session.client("glue")
    s3 = session.client("s3")
    b = args.bucket

    if args.logs:
        runs = glue.get_job_runs(JobName=job_name, MaxResults=1).get("JobRuns", [])
        if not runs:
            print(f"no runs found for {job_name}")
            return 1
        r = runs[0]
        print(f"run {r['Id']}: {r['JobRunState']}")
        print(f"  started : {r.get('StartedOn')}")
        print(f"  duration: {r.get('ExecutionTime')}s")
        if r.get("ErrorMessage"):
            print(f"  ERROR   : {r['ErrorMessage']}")
        print(f"  logs    : /aws-glue/jobs/output  (stream {r['Id']})")
        return 0 if r["JobRunState"] == "SUCCEEDED" else 1

    # ---- ship the code -----------------------------------------------------
    print("Step 1/3: upload job script + shared transforms")
    script_uri = upload(s3, b, JOB_SCRIPT, "code/glue_visual_etl_job.py")
    # gas_transforms.py rides along as --extra-py-files so `import
    # gas_transforms` resolves inside the job, keeping ONE copy of the pipeline
    # logic shared by Glue, EMR, and the notebook.
    transforms_uri = upload(s3, b, TRANSFORMS, "code/gas_transforms.py")

    # ---- create or update the job -----------------------------------------
    print("Step 2/3: create/update the Glue job")
    job_def = dict(
        Role=args.role_arn,
        GlueVersion="4.0",
        NumberOfWorkers=args.workers,
        WorkerType="G.1X",
        Timeout=args.timeout_min,
        Command={"Name": "glueetl", "ScriptLocation": script_uri, "PythonVersion": "3"},
        DefaultArguments={
            "--job-language": "python",
            "--TempDir": f"s3://{b}/tmp/glue/",
            "--extra-py-files": transforms_uri,
            "--enable-metrics": "true",
            "--enable-continuous-cloudwatch-log": "true",
            # The pipeline's own paths. Overridable per run.
            "--observations_path": f"s3://{b}/raw/observations/",
            "--stations_path": f"s3://{b}/raw/stations/ghcnd_stations_ca.csv",
            "--counties_path": f"s3://{b}/raw/counties/ca_county_centroids.csv",
            "--consumption_path": f"s3://{b}/raw/consumption/cec_ng_county_monthly.csv",
            "--output_path": f"s3://{b}/processed/visual-etl/",
        },
        Tags={"Project": "sagemaker-unified-studio-demos"},
    )
    try:
        glue.create_job(Name=job_name, **job_def)
        print(f"  created job '{job_name}'")
    except glue.exceptions.AlreadyExistsException:
        # Tags are not accepted by update_job.
        glue.update_job(JobName=job_name, JobUpdate={k: v for k, v in job_def.items() if k != "Tags"})
        print(f"  updated job '{job_name}'")

    if not args.start:
        print("\nStep 3/3: skipped (pass --start to run it).")
        return 0

    # ---- run it ------------------------------------------------------------
    print(f"Step 3/3: starting run ({args.workers} x G.1X)")
    run_id = glue.start_job_run(JobName=job_name)["JobRunId"]
    print(f"  run id: {run_id}")

    last = None
    started = time.time()
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

    print()
    print(f"final state : {state}")
    print(f"exec time   : {run.get('ExecutionTime')}s")
    # DPU-seconds is what you actually pay for; print it so the cost is visible.
    dpu_hours = run.get("DPUSeconds", 0) / 3600.0 if run.get("DPUSeconds") else None
    if dpu_hours:
        print(f"DPU-hours   : {dpu_hours:.4f}  (~${dpu_hours * 0.44:.4f} at $0.44/DPU-hour)")
    if run.get("ErrorMessage"):
        print(f"ERROR       : {run['ErrorMessage']}")

    if state != "SUCCEEDED":
        print("\nFetch the driver log for detail:")
        print(f"  aws logs tail /aws-glue/jobs/error --log-stream-names {run_id} "
              f"--profile {args.profile} --region {args.region}")
        return 1

    print(f"\nWrote s3://{b}/processed/visual-etl/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
