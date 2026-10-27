"""
Verify every demo artifact, and print exactly where it is and how to run it.

This answers three questions in one command:

    1. Is the data actually there, and is it real?   (counts, not just "exists")
    2. Where do I find it?                           (S3 URI, resource name, console path)
    3. How do I run / rebuild it?                    (the literal command)

`prebake_demos.py --status` answers only the first, as a yes/no. This goes
further: it reads row counts out of Parquet footers, pulls real metrics off the
training and tuning jobs, and prints the console path for each artifact so you
can navigate straight to it in front of a room.

Read-only. Nothing is created, modified or deleted.

    python shared/verify_demos.py              # everything
    python shared/verify_demos.py --demo 3     # just what Demo 3 needs
    python shared/verify_demos.py --quiet      # one line per artifact
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
from shared import config
from shared.config import add_common_args

OK, BAD, WARN = "  [ OK ]", "  [MISSING]", "  [ warn ]"

# Which prebake artifacts each demo in DEMOS.md actually depends on.
DEMO_NEEDS = {
    1: ["raw"],
    2: ["raw", "processed"],
    3: ["raw", "processed"],
    4: ["splits"],
    5: ["features"],
    6: ["splits", "training"],
    7: ["training", "tuning"],
    8: ["tuning"],
    9: ["model", "clarify"],
    10: ["splits", "training"],
    11: ["splits"],
}


class Report:
    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet
        self.missing: list[str] = []

    def item(self, name: str, present: bool, facts: list, where: str, how: str) -> None:
        mark = OK if present else BAD
        print(f"{mark} {name}")
        if not present:
            self.missing.append(name)
        if self.quiet:
            return
        for f in facts:
            print(f"         {f}")
        if where:
            print(f"         where : {where}")
        if how:
            print(f"         run   : {how}")
        print()


def _pq_rows(s3fs, path: str):
    """Row count straight out of the Parquet footers -- no data is scanned."""
    import pyarrow.dataset as ds

    d = ds.dataset(path, filesystem=s3fs, format="parquet", partitioning="hive")
    return d.count_rows()


def main() -> int:
    p = argparse.ArgumentParser(description="Verify demo artifacts. Read-only.")
    add_common_args(p, role=False)
    p.add_argument("--demo", type=int, default=None, help="Only what this demo needs")
    p.add_argument("--quiet", action="store_true", help="One line per artifact")
    args = p.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm = session.client("sagemaker")
    s3 = session.client("s3")
    b = args.bucket
    R = args.region

    import pyarrow.fs as fs

    creds = session.get_credentials().get_frozen_credentials()
    s3fs = fs.S3FileSystem(
        access_key=creds.access_key, secret_key=creds.secret_key,
        session_token=creds.token, region=R,
    )

    want = set(DEMO_NEEDS.get(args.demo, [])) if args.demo else None

    def skip(key: str) -> bool:
        return want is not None and key not in want

    print("=" * 74)
    print(f"Demo artifact verification - account {config.ACCOUNT}, {R}")
    print(f"bucket s3://{b}")
    if args.demo:
        print(f"filtered to Demo {args.demo} (needs: {', '.join(sorted(want))})")
    print("=" * 74)
    print()

    rep = Report(args.quiet)

    # ------------------------------------------------------------------ raw
    if not skip("raw"):
        facts, present = [], False
        try:
            n = s3.list_objects_v2(Bucket=b, Prefix="raw/observations/").get("KeyCount", 0)
            tot = s3.list_objects_v2(Bucket=b, Prefix="raw/").get("KeyCount", 0)
            present = tot > 0
            years = s3.list_objects_v2(Bucket=b, Prefix="raw/observations/", Delimiter="/")
            yr = [c["Prefix"].split("YEAR=")[-1].strip("/") for c in years.get("CommonPrefixes", [])]
            facts.append(f"{tot} objects under raw/ ({n} observation parquet files)")
            if yr:
                facts.append(f"years: {min(yr)}..{max(yr)}  ({len(yr)} partitions)")
            for key, label in [
                ("raw/stations/ghcnd_stations_ca.csv", "CA weather stations"),
                ("raw/counties/ca_county_centroids.csv", "CA county centroids"),
                ("raw/consumption/cec_ng_county_monthly.csv", "CEC county therms"),
            ]:
                try:
                    h = s3.head_object(Bucket=b, Key=key)
                    facts.append(f"{label}: {h['ContentLength']:,} bytes")
                except Exception:
                    facts.append(f"{label}: MISSING ({key})")
                    present = False
        except Exception as exc:
            facts.append(f"error: {exc}")
        rep.item(
            "raw/  staged source data", present, facts,
            f"s3://{b}/raw/  |  console: S3 > {b} > raw/",
            "python 00-setup/stage_dataset.py --start-year 2015 --end-year 2024",
        )

    # ------------------------------------------------------ processed dataset
    if not skip("processed"):
        facts, present = [], False
        try:
            rows = _pq_rows(s3fs, f"{b}/processed/visual-etl")
            objs = s3.list_objects_v2(Bucket=b, Prefix="processed/visual-etl/").get("KeyCount", 0)
            present = rows > 0
            facts.append(f"rows: {rows:,}  (expected ~1,668,673)")
            facts.append(f"objects: {objs}, partitioned by obs_year / obs_month")
        except Exception as exc:
            facts.append(f"error: {exc}")
        rep.item(
            "processed/visual-etl/  the pipeline output", present, facts,
            f"s3://{b}/processed/visual-etl/",
            "python 01-data-prep/new-visual-etl/run_glue_job.py --start --workers 4",
        )

    # ---------------------------------------------------------- ML splits
    if not skip("splits"):
        facts, present = [], False
        try:
            import io
            import pandas as pd

            for name in ("train", "validation", "test"):
                o = s3.get_object(Bucket=b, Key=f"ml/gas/{name}/{name}.csv")
                df = pd.read_csv(io.BytesIO(o["Body"].read()))
                facts.append(
                    f"{name:11s} {len(df):>7,} rows x {len(df.columns)} cols, "
                    f"positive rate {df.iloc[:, 0].mean():.4f}"
                )
                if name == "train":
                    present = True
                    facts.append(f"            label column: '{df.columns[0]}' (first, as expected)")
                    leaks = [c for c in df.columns if "therm" in c.lower()]
                    facts.append(
                        f"            leak check: {'FAIL ' + str(leaks) if leaks else 'clean (no therms columns)'}"
                    )
        except Exception as exc:
            facts.append(f"error: {exc}")
        rep.item(
            "ml/gas/  train / validation / test", present, facts,
            f"s3://{b}/ml/gas/",
            "python shared/prepare_ml_data.py",
        )

    # -------------------------------------------------------- feature store
    if not skip("features"):
        facts, present = [], False
        try:
            name = config.resource("features")
            d = sm.describe_feature_group(FeatureGroupName=name)
            present = d["FeatureGroupStatus"] == "Created"
            facts.append(f"name: {name}  status: {d['FeatureGroupStatus']}")
            facts.append(f"features: {len(d['FeatureDefinitions'])}, "
                         f"id={d['RecordIdentifierFeatureName']}, time={d['EventTimeFeatureName']}")
            off = d.get("OfflineStoreConfig", {}).get("S3StorageConfig", {}).get("S3Uri")
            if off:
                facts.append(f"offline store: {off}")
        except Exception as exc:
            facts.append(f"not found: {type(exc).__name__}")
        rep.item(
            "Feature Store group", present, facts,
            f"console: SageMaker AI > Feature Store > Feature groups > {config.resource('features')}",
            "python 03-feature-store/feature_store_ingest.py",
        )

    # -------------------------------------------------------- training job
    if not skip("training"):
        facts, present = [], False
        try:
            # No MaxResults with NameContains -- SageMaker applies the limit
            # BEFORE the name filter and silently returns nothing.
            jobs = sm.list_training_jobs(
                NameContains=config.resource("train"), StatusEquals="Completed",
                SortBy="CreationTime", SortOrder="Descending",
            )["TrainingJobSummaries"]
            if jobs:
                present = True
                j = jobs[0]["TrainingJobName"]
                d = sm.describe_training_job(TrainingJobName=j)
                m = {x["MetricName"]: x["Value"] for x in d.get("FinalMetricDataList", [])}
                facts.append(f"job: {j}")
                facts.append(f"metrics: {', '.join(f'{k}={v:.4f}' for k, v in m.items())}")
                facts.append(f"billable: {d.get('BillableTimeInSeconds')}s on "
                             f"{d['ResourceConfig']['InstanceType']}")
                facts.append(f"artifact: {d['ModelArtifacts']['S3ModelArtifacts']}")
                facts.append(f"({len(jobs)} completed training job(s) match)")
        except Exception as exc:
            facts.append(f"error: {exc}")
        rep.item(
            "Completed training job", present, facts,
            "console: SageMaker AI > Training > Training jobs",
            "python 04-training/launch_training.py",
        )

    # ------------------------------------------------------------ tuning job
    if not skip("tuning"):
        facts, present = [], False
        try:
            tun = sm.list_hyper_parameter_tuning_jobs(
                NameContains=config.resource("hpo"),
                SortBy="CreationTime", SortOrder="Descending",
            )["HyperParameterTuningJobSummaries"]
            if tun:
                present = True
                name = tun[0]["HyperParameterTuningJobName"]
                d = sm.describe_hyper_parameter_tuning_job(HyperParameterTuningJobName=name)
                cnt = d["TrainingJobStatusCounters"]
                facts.append(f"job: {name}  status: {d['HyperParameterTuningJobStatus']}")
                facts.append(f"trials: {cnt.get('Completed', 0)} completed, "
                             f"{cnt.get('Failed', 0)} failed")
                best = d.get("BestTrainingJob")
                if best:
                    obj = best.get("FinalHyperParameterTuningJobObjectiveMetric", {})
                    facts.append(f"best: {best['TrainingJobName']}")
                    facts.append(f"  {obj.get('MetricName')} = {obj.get('Value')}")
                    hp = best.get("TunedHyperParameters", {})
                    facts.append(f"  tuned: {hp}")
        except Exception as exc:
            facts.append(f"error: {exc}")
        rep.item(
            "HPO sweep (the leaderboard)", present, facts,
            "console: SageMaker AI > Training > Hyperparameter tuning jobs",
            "python 05-experiments-tuning/launch_tuning.py",
        )

    # ----------------------------------------------------------- the Model
    if not skip("model"):
        facts, present = [], False
        try:
            name = config.resource("model")
            d = sm.describe_model(ModelName=name)
            present = True
            facts.append(f"name: {name}")
            c = d.get("PrimaryContainer", {})
            facts.append(f"artifact: {c.get('ModelDataUrl')}")
            facts.append("cost: none -- metadata only until something invokes it")
        except Exception:
            facts.append("no Model object; Clarify cannot run without one")
        rep.item(
            "SageMaker Model object", present, facts,
            f"console: SageMaker AI > Inference > Models > {config.resource('model')}",
            "python shared/create_model.py",
        )

    # --------------------------------------------------------------- clarify
    if not skip("clarify"):
        facts, present = [], False
        try:
            r = s3.list_objects_v2(Bucket=b, Prefix="clarify/")
            keys = [o["Key"] for o in r.get("Contents", [])]
            reports = [k for k in keys if k.endswith(("report.html", "report.pdf", "analysis.json"))]
            present = len(reports) > 0
            facts.append(f"{len(keys)} objects under clarify/")
            for k in reports[:6]:
                facts.append(f"  {k}")
            # Clarify runs AS a Processing job -- that is where you find it live.
            pj = sm.list_processing_jobs(NameContains="Clarify", MaxResults=5)
            for j in pj.get("ProcessingJobSummaries", [])[:4]:
                facts.append(f"  processing job: {j['ProcessingJobName']} "
                             f"[{j['ProcessingJobStatus']}]")
        except Exception as exc:
            facts.append(f"error: {exc}")
        rep.item(
            "Clarify bias + SHAP reports", present, facts,
            f"s3://{b}/clarify/  |  console: SageMaker AI > Processing > Processing jobs",
            f"python 06-clarify-debugger-groundtruth/clarify_bias_explainability.py "
            f"--model-name {config.resource('model')}",
        )

    # ----------------------------------------------------------------- done
    print("=" * 74)
    if rep.missing:
        print(f"MISSING ({len(rep.missing)}):")
        for m in rep.missing:
            print(f"  - {m}")
        print("\nThe 'run' line under each shows how to build it, or:")
        print("  python shared/prebake_demos.py --all")
        return 1
    print("ALL VERIFIED - every artifact is present with real data.")
    if args.demo:
        print(f"Demo {args.demo} is safe to give.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
