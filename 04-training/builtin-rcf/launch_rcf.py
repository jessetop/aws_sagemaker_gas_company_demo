"""
Module 3, slide 13 -- "Demo (Optional): Built-in algorithm" with Random Cut Forest.

The slide asks for exactly four things: launch a notebook, import it in Studio,
set up the libraries for a built-in algorithm, and train with Random Cut Forest.
The speaker notes say to STOP after training and not continue to inference.
This script is that demo, on the gas data instead of a stock example.

WHY RANDOM CUT FOREST IS THE RIGHT BUILT-IN TO SHOW A UTILITY
--------------------------------------------------------------
Every other model in this series is supervised: we built a `high_demand` label
and asked "can you predict it". RCF needs NO LABEL. You hand it the feature
matrix and it tells you which rows do not look like the others.

That matters to a gas utility because the expensive surprises are the ones
nobody labelled in advance -- a cold snap that blows through the demand
forecast, a meter reporting consumption the weather cannot explain, a station
whose readings drift. You cannot train a classifier for "the thing I did not
expect". RCF is the shape of model you reach for instead.

HOW IT WORKS, IN ONE BREATH
---------------------------
Build many random binary trees over random subsets of the data, cutting on a
random feature at a random value, over and over. Points in dense regions need
many cuts to isolate; an outlier gets isolated in very few. The anomaly score
is essentially how SHALLOW the point lands, averaged over the forest. That is
the whole idea -- no labels, no distance metric to tune, no assumption that the
data is Gaussian.

THE TWO THINGS STUDENTS ALWAYS ASK
----------------------------------
1. "What is a good score?" There is no absolute scale. RCF scores are relative
   to this dataset. The convention is to flag anything above
   mean + 3 * stddev of the scores, which means you are choosing an alert
   budget, not discovering a truth.
2. "Why is feature_dim a hyperparameter?" Because the built-in containers take
   headerless CSV and cannot see your schema. If feature_dim disagrees with the
   real column count the job fails at startup -- the single most common way
   this demo breaks. It is computed from the data below, never typed by hand.

COST: ml.m5.large for 2-4 minutes. Cents. No endpoint is created -- the slide
says stop before inference, which is also why this is safe to re-run.

Usage:
    python 04-training/builtin-rcf/launch_rcf.py              # prepare + train + wait
    python 04-training/builtin-rcf/launch_rcf.py --status     # is the artifact baked?
"""

import argparse
import io
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

# The supervised demos' training matrix. We reuse it deliberately: showing the
# room the SAME table going into a model that ignores the label is the cleanest
# way to make "supervised vs unsupervised" land.
SOURCE_KEY = "ml/gas/autopilot/train.csv"
RCF_PREFIX = "ml/gas/rcf"

DONE = {"Completed", "Failed", "Stopped"}


def prepare(s3, bucket: str) -> int:
    """Drop the label column and the header. Returns feature_dim.

    RCF takes headerless CSV. Leaving `high_demand` in would be target leakage
    of the most literal kind -- the model would be handed the answer it is
    supposed to be ignorant of, and the feature it found most useful for
    isolating points would be the label itself.
    """
    body = s3.get_object(Bucket=bucket, Key=SOURCE_KEY)["Body"].read().decode("utf-8")
    lines = body.strip().split("\n")
    header = lines[0].split(",")
    label_idx = header.index("high_demand")
    kept = [c for i, c in enumerate(header) if i != label_idx]

    out = io.StringIO()
    for row in lines[1:]:
        cells = row.split(",")
        out.write(",".join(c for i, c in enumerate(cells) if i != label_idx) + "\n")
    payload = out.getvalue().encode("utf-8")

    s3.put_object(Bucket=bucket, Key=f"{RCF_PREFIX}/train/train.csv", Body=payload)
    # Keep the column order next to the data: scores come back as bare numbers
    # and you will want to know which column was which.
    s3.put_object(Bucket=bucket, Key=f"{RCF_PREFIX}/feature_columns.txt",
                  Body=("\n".join(kept)).encode("utf-8"))
    print(f"  dropped label column '{header[label_idx]}' (index {label_idx})")
    print(f"  {len(lines) - 1} rows x {len(kept)} features -> s3://{bucket}/{RCF_PREFIX}/train/")
    return len(kept)


def main() -> int:
    p = argparse.ArgumentParser(description="Module 3 slide 13: built-in algorithm (RCF).")
    add_common_args(p)
    p.add_argument("--status", action="store_true",
                   help="Report whether the artifact exists; change nothing")
    p.add_argument("--num-trees", type=int, default=50)
    p.add_argument("--num-samples-per-tree", type=int, default=256)
    args = p.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm = session.client("sagemaker")
    s3 = session.client("s3")
    job_prefix = config.resource("rcf")

    # No MaxResults alongside NameContains: SageMaker applies the limit to the
    # page it fetches BEFORE the name filter, so MaxResults=1 silently returns
    # nothing once another job is newer. This bit several scripts in this repo.
    done = sm.list_training_jobs(
        NameContains=job_prefix, StatusEquals="Completed",
        SortBy="CreationTime", SortOrder="Descending",
    )["TrainingJobSummaries"]
    if args.status:
        if done:
            j = done[0]["TrainingJobName"]
            d = sm.describe_training_job(TrainingJobName=j)
            print(f"BAKED  {j}")
            print(f"  model: {d['ModelArtifacts']['S3ModelArtifacts']}")
            return 0
        print("NOT BAKED - run this script without --status")
        return 1

    print("Step 1/3: strip the label, write headerless CSV")
    feature_dim = prepare(s3, args.bucket)

    print("Step 2/3: resolve the built-in RCF container")
    # This is the "set up the libraries to use a built-in algorithm" beat on the
    # slide. There is no training script and no requirements.txt: the algorithm
    # ships as an AWS-maintained container image and you address it by name.
    # That IS the point of a built-in -- you bring data and hyperparameters.
    import sagemaker
    image = sagemaker.image_uris.retrieve("randomcutforest", args.region)
    print(f"  {image}")

    job = f"{job_prefix}-{time.strftime('%y%m%d-%H%M')}"
    print(f"Step 3/3: training job {job}")
    sm.create_training_job(
        TrainingJobName=job,
        AlgorithmSpecification={"TrainingImage": image, "TrainingInputMode": "File"},
        RoleArn=args.role_arn,
        HyperParameters={
            "num_trees": str(args.num_trees),
            "num_samples_per_tree": str(args.num_samples_per_tree),
            # Computed, never typed. A mismatch here is the #1 cause of this
            # job failing at startup.
            "feature_dim": str(feature_dim),
        },
        InputDataConfig=[{
            "ChannelName": "train",
            "DataSource": {"S3DataSource": {
                "S3DataType": "S3Prefix",
                "S3Uri": f"s3://{args.bucket}/{RCF_PREFIX}/train/",
                "S3DataDistributionType": "ShardedByS3Key",
            }},
            # label_size=0 is how you tell a built-in "there is no label column
            # in this file". Omit it and RCF treats the first feature as a label.
            "ContentType": "text/csv;label_size=0",
            "CompressionType": "None",
        }],
        OutputDataConfig={"S3OutputPath": f"s3://{args.bucket}/{RCF_PREFIX}/output/"},
        ResourceConfig={"InstanceType": "ml.m5.large", "InstanceCount": 1, "VolumeSizeInGB": 10},
        StoppingCondition={"MaxRuntimeInSeconds": 900},
    )

    last, started = None, time.time()
    while True:
        d = sm.describe_training_job(TrainingJobName=job)
        st = d["TrainingJobStatus"]
        if st != last:
            print(f"  [{time.time() - started:5.0f}s] {st}")
            last = st
        if st in DONE:
            break
        time.sleep(20)

    if st != "Completed":
        print(f"FAILED: {d.get('FailureReason')}")
        return 1
    print(f"\nmodel: {d['ModelArtifacts']['S3ModelArtifacts']}")
    print(f"billable seconds: {d.get('BillableTimeInSeconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
