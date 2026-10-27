"""
Pipeline step — evaluate the trained model on the held-out test split.

Runs as a SageMaker Processing job: load the model artifact, score the test CSV,
and write evaluation.json. The pipeline reads `binary_classification_metrics.auc`
from this file in a ConditionStep — the model is only registered if it clears the
AUC bar (the quality gate that makes a pipeline "real").

Contract:
  input : /opt/ml/processing/model  (model.tar.gz)   + /opt/ml/processing/test
  output: /opt/ml/processing/evaluation/evaluation.json
"""

import glob
import json
import os
import tarfile

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score

MODEL_DIR = "/opt/ml/processing/model"
TEST_DIR = "/opt/ml/processing/test"
OUT_DIR = "/opt/ml/processing/evaluation"


def main() -> None:
    # Unpack model.tar.gz -> model.joblib
    with tarfile.open(os.path.join(MODEL_DIR, "model.tar.gz")) as tar:
        tar.extractall(MODEL_DIR)
    model = joblib.load(os.path.join(MODEL_DIR, "model.joblib"))

    # Test split is headerless, label first column (preprocess.py contract).
    test_csv = glob.glob(os.path.join(TEST_DIR, "*.csv"))[0]
    df = pd.read_csv(test_csv, header=None)
    y = df.iloc[:, 0]
    X = df.iloc[:, 1:]

    proba = model.predict_proba(X)[:, 1]
    preds = (proba >= 0.5).astype(int)
    acc = float(accuracy_score(y, preds))
    auc = float(roc_auc_score(y, proba))
    print(f"evaluation: accuracy={acc:.4f} auc={auc:.4f}")

    # The metric-report shape SageMaker Model Quality / Pipelines expect.
    report = {
        "binary_classification_metrics": {
            "accuracy": {"value": acc, "standard_deviation": "NaN"},
            "auc": {"value": auc, "standard_deviation": "NaN"},
        }
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "evaluation.json"), "w") as f:
        json.dump(report, f)


if __name__ == "__main__":
    main()
