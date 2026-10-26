"""
Custom SageMaker training script (Kiro Req 2) — shared by old and new way.

Trains a scikit-learn classifier to predict `high_demand` from the engineered
gas/weather features. Written to the SageMaker training contract so the SAME script runs as a
classic SageMaker AI training job AND as a Unified Studio project training job —
the launcher changes, the script does not.

SageMaker contract (see inline notes):
  - Hyperparameters arrive as command-line args.
  - Input data is at SM_CHANNEL_TRAIN / SM_CHANNEL_VALIDATION.
  - The fitted model is written to SM_MODEL_DIR.
  - Metrics are printed to stdout as `name=value` so SageMaker can scrape them.
This file is also the inference entry point (model_fn/predict_fn) for Module 7.
"""

import argparse
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score


def _read_channel(path: str) -> pd.DataFrame:
    """Read the single CSV in a SageMaker input channel directory.

    Raises FileNotFoundError if the channel is missing or empty (Kiro Req 2.7).
    """
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(f"Input channel path does not exist: {path}")
    csvs = [f for f in os.listdir(path) if f.endswith(".csv")]
    if not csvs:
        raise FileNotFoundError(f"No CSV data files found in channel: {path}")
    csv_path = os.path.join(path, csvs[0])
    # Header-robust: the standalone CSVs have a header row; the pipeline's
    # preprocess.py writes headerless (label-first) CSVs. Detect which.
    with open(csv_path) as fh:
        first = fh.readline().strip().split(",")

    def _is_num(tok: str) -> bool:
        try:
            float(tok)
            return True
        except ValueError:
            return False

    has_header = not all(_is_num(t) for t in first)
    return pd.read_csv(csv_path, header=0 if has_header else None)


def _validate_hyperparameters(args) -> None:
    """Range-check hyperparameters and fail loudly (Kiro Req 2.6)."""
    if not 0.0001 <= args.learning_rate <= 1.0:
        raise ValueError("learning_rate must be between 0.0001 and 1.0")
    if not 1 <= args.n_estimators <= 1000:
        raise ValueError("n_estimators must be between 1 and 1000")
    if not 1 <= args.max_depth <= 20:
        raise ValueError("max_depth must be between 1 and 20")


def train(args) -> None:
    _validate_hyperparameters(args)

    # T-contract: read train + validation from the channel paths SageMaker mounts.
    train_df = _read_channel(args.train)
    val_df = _read_channel(args.validation)

    # Label is the first column (see prepare_ml_data.py).
    y_train, X_train = train_df.iloc[:, 0], train_df.iloc[:, 1:]
    y_val, X_val = val_df.iloc[:, 0], val_df.iloc[:, 1:]

    model = GradientBoostingClassifier(
        learning_rate=args.learning_rate,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # Compute + emit metrics. The `name=value` lines are what a SageMaker metric
    # definition / tuning objective regex matches against (Kiro Req 2.3, 6.2).
    val_pred = model.predict(X_val)
    val_proba = model.predict_proba(X_val)[:, 1]
    acc = accuracy_score(y_val, val_pred)
    auc = roc_auc_score(y_val, val_proba)
    print(f"validation_accuracy={acc:.4f}")
    print(f"validation_auc={auc:.4f}")

    # Persist the model to SM_MODEL_DIR so SageMaker tars it up to S3.
    os.makedirs(args.model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(args.model_dir, "model.joblib"))
    print(f"saved model to {args.model_dir}")


# ----- Inference handlers (used by the Module 7 endpoint) -------------------
def model_fn(model_dir):
    """Load the model for serving."""
    return joblib.load(os.path.join(model_dir, "model.joblib"))


def predict_fn(input_data, model):
    """Return P(high_demand) for each input row.

    The container's CSV input_fn hands a single row back as a 1D array; reshape
    to 2D so predict_proba accepts it (works for batches too).
    """
    arr = np.asarray(input_data, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return model.predict_proba(arr)[:, 1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Hyperparameters (Kiro Req 2.1 / 5.3).
    parser.add_argument("--learning-rate", type=float, default=0.1)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=3)
    # SageMaker injects these env vars; argparse reads them as defaults.
    parser.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "."))
    parser.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN"))
    parser.add_argument(
        "--validation", default=os.environ.get("SM_CHANNEL_VALIDATION")
    )
    train(parser.parse_args())
