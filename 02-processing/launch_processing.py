"""
Demo 4 -- run the ML-prep step as a real SageMaker Processing job.

WHY THIS SCRIPT EXISTS
----------------------
`08-pipelines/preprocess.py` was only ever invoked from inside the full
SageMaker Pipeline, so there was no way to produce a single Completed Processing
job to point at. That made Demo 4 a talk-through: the only Processing jobs in
the account belonged to Autopilot and Clarify, which are somebody else's jobs
with somebody else's names on them. This runs the same step standalone.

WHAT THE DEMO IS ACTUALLY ABOUT
-------------------------------
Processing is the answer to "I have a Python script and 1.67 million rows, and
my laptop is not going to do this." You hand SageMaker a script, an instance
type and S3 paths; it starts the instance, mounts your input, runs the script,
copies the outputs back, and shuts the instance down. You pay for the minutes
it ran.

The three things worth pointing at in the console afterwards:

  * **Input/output configuration.** The script never touches S3. It reads
    /opt/ml/processing/input/data and writes /opt/ml/processing/output/... and
    SageMaker does the copying. That is the whole contract -- which is why the
    same file runs unchanged as a pipeline step.
  * **The container.** A stock AWS scikit-learn image. No Dockerfile here.
  * **Billable seconds.** The instance exists only for the job. There is
    nothing to remember to turn off, which is the contrast with Canvas and
    endpoints.

COST: one ml.m5.xlarge for ~4-6 minutes. Two cents. Nothing survives the job.

Usage:
    python 02-processing/launch_processing.py            # run it, wait, report
    python 02-processing/launch_processing.py --status    # is one baked already?
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
from shared import config
from shared.config import add_common_args

SCRIPT = _os.path.join(_root, "08-pipelines", "preprocess.py")
DONE = {"Completed", "Failed", "Stopped"}


def main() -> int:
    p = argparse.ArgumentParser(description="Demo 4: ML prep as a Processing job.")
    add_common_args(p)
    p.add_argument("--status", action="store_true",
                   help="Report whether a Completed job exists; change nothing")
    p.add_argument("--instance-type", default="ml.m5.xlarge")
    args = p.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm = session.client("sagemaker")
    job_prefix = config.resource("prep")

    # No MaxResults alongside NameContains: SageMaker applies the limit to the
    # page it fetches BEFORE the name filter, so MaxResults=1 silently returns
    # nothing as soon as another job is newer.
    existing = sm.list_processing_jobs(
        NameContains=job_prefix, StatusEquals="Completed",
        SortBy="CreationTime", SortOrder="Descending",
    )["ProcessingJobSummaries"]

    if args.status:
        if existing:
            name = existing[0]["ProcessingJobName"]
            d = sm.describe_processing_job(ProcessingJobName=name)
            print(f"BAKED  {name}")
            print(f"  instance: {d['ProcessingResources']['ClusterConfig']['InstanceType']}")
            print(f"  outputs : {len(d.get('ProcessingOutputConfig', {}).get('Outputs', []))}")
            return 0
        print("NOT BAKED - run this script without --status")
        return 1

    import sagemaker
    from sagemaker.processing import ProcessingInput, ProcessingOutput
    from sagemaker.sklearn.processing import SKLearnProcessor

    sm_sess = sagemaker.Session(boto_session=session)
    b = args.bucket

    # ml.m5.xlarge rather than m5.large: the step reads 1.67M rows of parquet
    # into pandas, and the smaller instance has 8 GB which is uncomfortably
    # close. Two cents either way.
    proc = SKLearnProcessor(
        framework_version="1.2-1",
        role=args.role_arn,
        instance_type=args.instance_type,
        instance_count=1,
        base_job_name=job_prefix,
        sagemaker_session=sm_sess,
    )

    out_prefix = f"s3://{b}/processed/demo4-processing"

    # Upload the script and pass an s3:// URI rather than a local path.
    #
    # On Windows the SDK runs the local path through urlparse, so
    # "C:\...\preprocess.py" is read as url scheme "c" and rejected with
    # "url scheme c is not recognized". Handing it an S3 URI avoids the
    # question entirely and makes the run reproducible from any machine.
    code_key = "code/preprocess.py"
    session.client("s3").upload_file(SCRIPT, b, code_key)
    code_uri = f"s3://{b}/{code_key}"

    print(f"input : s3://{b}/processed/visual-etl/")
    print(f"output: {out_prefix}/")
    print(f"script: {code_uri}")
    print()

    proc.run(
        code=code_uri,
        inputs=[ProcessingInput(
            source=f"s3://{b}/processed/visual-etl/",
            # /data, not the parent: the SDK mounts this run's code at
            # input/code/, and a parquet dataset read of the parent would
            # try to parse preprocess.py as parquet.
            destination="/opt/ml/processing/input/data",
        )],
        outputs=[
            ProcessingOutput(output_name=name,
                             source=f"/opt/ml/processing/output/{name}",
                             destination=f"{out_prefix}/{name}")
            for name in ("train", "validation", "test")
        ],
        wait=False,
    )

    name = proc.latest_job.job_name
    print(f"job: {name}")

    last, started = None, time.time()
    while True:
        d = sm.describe_processing_job(ProcessingJobName=name)
        st = d["ProcessingJobStatus"]
        if st != last:
            print(f"  [{time.time() - started:5.0f}s] {st}")
            last = st
        if st in DONE:
            break
        time.sleep(20)

    if st != "Completed":
        print(f"FAILED: {d.get('FailureReason')}")
        print(f"  logs: aws logs tail /aws/sagemaker/ProcessingJobs --log-stream-name-prefix {name}")
        return 1

    secs = None
    if d.get("ProcessingEndTime") and d.get("ProcessingStartTime"):
        secs = (d["ProcessingEndTime"] - d["ProcessingStartTime"]).total_seconds()
    print()
    print(f"instance        : {d['ProcessingResources']['ClusterConfig']['InstanceType']}")
    if secs:
        print(f"processing time : {secs:.0f}s")
    print(f"outputs         : {out_prefix}/")
    print()
    print("Console: SageMaker AI > Processing > Processing jobs > " + name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
