"""
Pre-bake every artifact the 5-minute demos need. Run this BEFORE class.

THE COOKING SHOW PROBLEM
------------------------
A SageMaker training job takes 3 minutes. An HPO sweep takes 15. A Clarify SHAP
job takes 10. Nobody watches a progress bar for 15 minutes, and a demo that
depends on a live job finishing is a demo that can fail in front of a room.

So every demo follows the cooking-show pattern:

    1. show the console where you'd configure the thing
    2. click Start -- then cancel, or just don't wait
    3. cut to the one that is already finished, and talk about the result

This script bakes the cakes. It creates the finished artifacts so that when you
open Experiments, Training Jobs, the Model Registry or Clarify during class,
there is already something real and gas-specific sitting there.

Run it the morning of, or the night before. Total cost is a few dollars and
most of that is the HPO sweep.

    python shared/prebake_demos.py --all
    python shared/prebake_demos.py --only features,training
    python shared/prebake_demos.py --list
    python shared/prebake_demos.py --status      # what already exists?

Deliberately NOT baked: a live inference endpoint. An endpoint bills by the
hour for as long as it exists, and 07-deployment/deploy_and_infer.py creates and
deletes one inside a single demo anyway. Bake it and you will forget it.
"""

import argparse
import subprocess
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

PY = sys.executable


# Each step: what it is, what it runs, roughly how long, roughly what it costs,
# and a probe that answers "is this already baked?" so re-runs are cheap.
STEPS = [
    {
        "key": "data",
        "title": "Processed dataset (Glue pipeline)",
        "cmd": ["01-data-prep/new-visual-etl/run_glue_job.py", "--start", "--workers", "4"],
        "mins": 10,
        "cost": "$0.30",
        "feeds": "Demo: Data Wrangler, EMR/Spark, Processing",
    },
    {
        "key": "splits",
        "title": "ML train/validation/test splits",
        "cmd": ["shared/prepare_ml_data.py"],
        "mins": 2,
        "cost": "free (local)",
        "feeds": "everything downstream",
    },
    {
        "key": "features",
        "title": "Feature Store group + ingested records",
        "cmd": ["03-feature-store/feature_store_ingest.py"],
        "mins": 3,
        "cost": "cents",
        "feeds": "Demo: Feature Store",
    },
    {
        "key": "training",
        "title": "A completed training job",
        "cmd": ["04-training/launch_training.py"],
        "mins": 4,
        "cost": "cents",
        "feeds": "Demo: Training, Experiments, Model Registry, Clarify",
    },
    {
        "key": "tuning",
        "title": "A completed HPO sweep (the leaderboard)",
        "cmd": ["05-experiments-tuning/launch_tuning.py"],
        "mins": 15,
        "cost": "~$1",
        "feeds": "Demo: Experiments compare, HPO",
    },
    {
        "key": "clarify",
        "title": "Clarify bias + SHAP reports",
        "cmd": ["06-clarify-debugger-groundtruth/clarify_bias_explainability.py"],
        "mins": 12,
        "cost": "~$0.50",
        "feeds": "Demo: Clarify",
    },
]


def probe(session, bucket: str) -> dict:
    """Answer 'what is already baked?' so you can re-run only what is missing."""
    sm = session.client("sagemaker")
    s3 = session.client("s3")
    state = {}

    def _s3_has(prefix: str) -> bool:
        r = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
        return r.get("KeyCount", 0) > 0

    try:
        state["data"] = _s3_has("processed/visual-etl/")
    except Exception:
        state["data"] = None
    try:
        state["splits"] = _s3_has("ml/gas/train/")
    except Exception:
        state["splits"] = None

    try:
        groups = sm.list_feature_groups(NameContains=config.PREFIX)["FeatureGroupSummaries"]
        state["features"] = len(groups) > 0
    except Exception:
        state["features"] = None

    try:
        jobs = sm.list_training_jobs(
            NameContains=config.resource("train"), StatusEquals="Completed", MaxResults=1
        )["TrainingJobSummaries"]
        state["training"] = len(jobs) > 0
    except Exception:
        state["training"] = None

    try:
        tun = sm.list_hyper_parameter_tuning_jobs(
            NameContains=config.resource("hpo"), MaxResults=1
        )["HyperParameterTuningJobSummaries"]
        state["tuning"] = len(tun) > 0
    except Exception:
        state["tuning"] = None

    try:
        state["clarify"] = _s3_has("clarify/")
    except Exception:
        state["clarify"] = None

    return state


def run_step(step: dict, extra: list) -> bool:
    cmd = [PY, _os.path.join(_root, step["cmd"][0])] + step["cmd"][1:] + extra
    print()
    print("=" * 70)
    print(f"BAKING: {step['title']}")
    print(f"  ~{step['mins']} min, ~{step['cost']}")
    print(f"  $ {' '.join(step['cmd'])}")
    print("=" * 70)
    started = time.time()
    # Stream the child's output so a long step does not look hung.
    result = subprocess.run(cmd, cwd=_root)
    took = (time.time() - started) / 60.0
    if result.returncode != 0:
        print(f"\n!! FAILED after {took:.1f} min: {step['title']}")
        print(f"   exit code {result.returncode}")
        return False
    print(f"\n   done in {took:.1f} min")
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description="Pre-bake the finished artifacts the 5-minute demos point at."
    )
    add_common_args(p)
    p.add_argument("--all", action="store_true", help="Bake every step")
    p.add_argument("--only", default="", help="Comma-separated step keys to bake")
    p.add_argument("--skip", default="", help="Comma-separated step keys to skip")
    p.add_argument("--list", action="store_true", help="List the steps and exit")
    p.add_argument("--status", action="store_true", help="Show what is already baked and exit")
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-bake steps that already look done (default: skip them)",
    )
    args = p.parse_args()

    if args.list:
        print(f"{'key':10} {'~min':>5} {'cost':>12}  what it feeds")
        print("-" * 78)
        total = 0
        for s in STEPS:
            print(f"{s['key']:10} {s['mins']:>5} {s['cost']:>12}  {s['feeds']}")
            total += s["mins"]
        print("-" * 78)
        print(f"{'TOTAL':10} {total:>5} min end to end (mostly unattended)")
        return 0

    session = boto3.Session(profile_name=args.profile, region_name=args.region)

    if args.status:
        state = probe(session, args.bucket)
        print(f"{'key':10} {'baked?':10} what it feeds")
        print("-" * 78)
        for s in STEPS:
            v = state.get(s["key"])
            mark = "yes" if v else ("UNKNOWN" if v is None else "no")
            print(f"{s['key']:10} {mark:10} {s['feeds']}")
        print()
        missing = [s["key"] for s in STEPS if state.get(s["key"]) is False]
        if missing:
            print(f"not baked: {','.join(missing)}")
            print(f"  python shared/prebake_demos.py --only {','.join(missing)}")
        else:
            print("everything looks baked. You are ready to demo.")
        return 0

    if not args.all and not args.only:
        p.error("pass --all, or --only <keys>, or --list / --status")

    wanted = [s["key"] for s in STEPS] if args.all else [k.strip() for k in args.only.split(",")]
    skip = {k.strip() for k in args.skip.split(",") if k.strip()}
    unknown = set(wanted) - {s["key"] for s in STEPS}
    if unknown:
        p.error(f"unknown step(s): {sorted(unknown)}. Try --list")

    # Pass the standard AWS args through to each child script.
    extra = ["--profile", args.profile, "--region", args.region, "--bucket", args.bucket]

    state = {} if args.force else probe(session, args.bucket)

    plan = [s for s in STEPS if s["key"] in wanted and s["key"] not in skip]
    already = [s["key"] for s in plan if state.get(s["key"])]
    plan = [s for s in plan if not state.get(s["key"])]

    if already:
        print(f"already baked, skipping: {','.join(already)}  (use --force to redo)")
    if not plan:
        print("nothing to do.")
        return 0

    print(f"plan: {' -> '.join(s['key'] for s in plan)}")
    print(f"estimated {sum(s['mins'] for s in plan)} min")

    failed = []
    for step in plan:
        # Steps are ordered by dependency; a failure early makes the rest
        # meaningless, so stop rather than cascade confusing errors.
        if not run_step(step, extra):
            failed.append(step["key"])
            print("\nStopping: later steps depend on this one.")
            break

    print()
    print("=" * 70)
    if failed:
        print(f"FAILED: {','.join(failed)}")
        print("Fix the error above, then re-run; completed steps are skipped automatically.")
        return 1
    print("All requested artifacts are baked. Run --status to confirm.")
    print("Now read DEMOS.md for the per-service 5-minute scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
