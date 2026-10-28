"""
Demo 7b — log the feature-ablation arc to SageMaker's managed MLflow.

Trains the SAME question four ways and logs each as an MLflow run, so the
Demo 7 arc ("0.92 and we were delighted, then we looked") exists inside MLflow
as a comparable set of runs instead of only as a slide.

  all features   -> the number everyone is happy with
  calendar only  -> obs_month + season_* + is_heating_season + is_weekend
  weather only   -> everything the weather station actually measured
  deseasonalised -> the punchline. Same features, harder question, coin flip.

A shuffled-label control was tried here first and REMOVED on purpose. It is the
obvious control and it does not work on this dataset: measured across seeds it
returned AUC 0.3225 / 0.5073 / 0.3404 instead of centring on 0.50. That is not a
bug in the shuffle, it is the group structure -- the label is a county-month
aggregate, so the effective sample size is ~5,530 groups rather than 150,000
rows, and AUC swings hard around chance. Do not put it back without re-measuring.

Target is an MLflow APP (`mlflow-app/...`), not an MLflow tracking SERVER.
That distinction is the whole cost story:

  * MLflow App     -- serverless, no Start/Stop, **$0 at rest**. Verified via
                      Cost Explorer: Aug 2026 and Sep 2026 were $0.00 for all of
                      SageMaker while this app existed the entire time.
  * Tracking Server-- $0.60/hr Small in us-east-1, billing from Created until
                      Deleted, no idle shutdown. ~$432/month if forgotten.

Both are addressed by ARN as the MLflow tracking URI, so the only thing that
tells them apart is the ARN itself. Check which one you are pointing at before
anyone tells you MLflow on SageMaker is expensive.

Usage:
    python 05-experiments-tuning/mlflow_log_ablation.py
    python 05-experiments-tuning/mlflow_log_ablation.py --sample-rows 25000
"""

import argparse
import io
import sys

import boto3
import mlflow
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args

# The app that already exists in the account, orphaned from a domain that was
# deleted in July. Free, so it was never noticed.
DEFAULT_ARN = "arn:aws:sagemaker:us-east-1:029331796573:mlflow-app/app-D7XHWR77EVWN"

LABEL = "high_demand"
CALENDAR = ["obs_month", "season_Spring", "season_Summer", "season_Winter",
            "is_heating_season", "is_weekend"]

# Same hyperparameters as the baked baseline training job, so the MLflow number
# is comparable to the SageMaker Experiments number rather than merely similar.
HP = {"n_estimators": 150, "learning_rate": 0.1, "max_depth": 3, "random_state": 42}


def _read_csv(s3, bucket: str, key: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(s3.get_object(Bucket=bucket, Key=key)["Body"].read()))


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument("--tracking-arn", default=DEFAULT_ARN)
    p.add_argument("--experiment", default="gas-demand-the-honest-metric")
    p.add_argument("--prefix", default="ml/gas")
    p.add_argument("--deseason-prefix", default="ml/gas-deseason",
                   help="splits built with prepare_ml_data.py --deseasonalize. Written to a "
                        "SEPARATE prefix on purpose -- regenerating ml/gas would overwrite the "
                        "baked splits every other Day 2 demo depends on.")
    p.add_argument("--sample-rows", type=int, default=0,
                   help="subsample training rows (0 = all). Studio t3.medium wants ~25000.")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = boto_sess.client("s3")

    train = _read_csv(s3, args.bucket, f"{args.prefix}/train/train.csv")
    valid = _read_csv(s3, args.bucket, f"{args.prefix}/validation/validation.csv")
    if args.sample_rows and args.sample_rows < len(train):
        train = train.sample(n=args.sample_rows, random_state=42)
    print(f"train {train.shape}  validation {valid.shape}")

    features = [c for c in train.columns if c != LABEL]
    weather = [c for c in features if c not in CALENDAR]

    # The deseasonalised run is the same features and the same code -- only the
    # LABEL changed, from "was this a top-quartile month for this county" to
    # "was this January unusual for this county's Januaries".
    ds_train = _read_csv(s3, args.bucket, f"{args.deseason_prefix}/train/train.csv")
    ds_valid = _read_csv(s3, args.bucket, f"{args.deseason_prefix}/validation/validation.csv")
    if args.sample_rows and args.sample_rows < len(ds_train):
        ds_train = ds_train.sample(n=args.sample_rows, random_state=42)

    variants = [
        ("all-features", features, train, valid,
         "every column we engineered"),
        ("calendar-only", CALENDAR, train, valid,
         "month and season alone -- no weather reading at all"),
        ("weather-only", weather, train, valid,
         "what the station measured, with the calendar removed"),
        ("deseasonalised-label", features, ds_train, ds_valid,
         "same features, harder question: was THIS January unusual for this county"),
    ]

    mlflow.set_tracking_uri(args.tracking_arn)
    mlflow.set_experiment(args.experiment)
    print(f"tracking uri : {args.tracking_arn}")
    print(f"experiment   : {args.experiment}\n")

    results = []
    for name, cols, tr_df, va_df, blurb in variants:
        with mlflow.start_run(run_name=name):
            mlflow.log_params(HP)
            mlflow.log_param("variant", name)
            mlflow.log_param("n_features", len(cols))
            mlflow.log_param("n_train_rows", len(tr_df))
            mlflow.log_param("label_definition",
                             "within county AND month-of-year" if "deseason" in name
                             else "within county")
            mlflow.set_tag("question", blurb)

            model = GradientBoostingClassifier(**HP)
            model.fit(tr_df[cols], tr_df[LABEL])

            proba = model.predict_proba(va_df[cols])[:, 1]
            pred = (proba >= 0.5).astype(int)
            auc = roc_auc_score(va_df[LABEL], proba)
            acc = accuracy_score(va_df[LABEL], pred)

            mlflow.log_metric("validation_auc", auc)
            mlflow.log_metric("validation_accuracy", acc)

            # Feature importance is the whole point of Demo 7 -- log it so the
            # "70% of the model is one column" finding is inspectable in the UI,
            # not just asserted on a slide.
            imp = sorted(zip(cols, model.feature_importances_),
                         key=lambda x: -x[1])
            for col, val in imp[:5]:
                mlflow.log_metric(f"importance__{col}", float(val))

            top = ", ".join(f"{c}={v:.3f}" for c, v in imp[:3])
            print(f"{name:<16} auc={auc:.4f}  acc={acc:.4f}  top: {top}")
            results.append((name, auc, acc, imp[0]))

    print("\n--- the arc ---")
    for name, auc, acc, top in results:
        print(f"  {name:<16} AUC {auc:.4f}   dominant feature: {top[0]} ({top[1]:.3f})")
    print(f"\nOpen the UI:  python {_os.path.relpath(__file__, _root)} --help  then see DEMOS.md Demo 7b")
    return 0


if __name__ == "__main__":
    sys.exit(main())
