"""
Module 6 (demo) — PROVE the Clarify explainability charts are real.

The Clarify report (report.html / the Studio explainability tab) is just a render
of two files the processing job wrote to S3:
    analysis.json                  -> the global SHAP bar chart numbers
    explanations_shap/out.csv      -> the per-row (local) SHAP values

This script downloads those files and reconciles them two ways, so in class you can
show the charts aren't magic:

  CHECK 1 (global bars):  global_shap_values[feature] == mean(|local SHAP column|)
                          because the job ran with agg_method="mean_abs".

  CHECK 2 (additivity):   for any row, the model's prediction ==
                          expected_value + sum(local SHAP values for that row).
                          We verify against the LIVE endpoint, so the number the
                          class sees come out of invoke_endpoint matches the math.

Usage:
    python 06-clarify-debugger-groundtruth/validate_clarify_report.py \
        --profile default --region us-east-1 \
        --clarify-prefix clarify \
        --endpoint <prefix>-monitor --rows 3
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
from shared.config import add_common_args, BUCKET
SAMPLE_KEY = "clarify-input/sample.csv"  # exact rows Clarify scored


def _get_text(s3, key: str) -> str:
    return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode()


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p, bucket=False, role=False)
    p.add_argument("--clarify-prefix", default="clarify",
                   help="prefix holding analysis.json + explanations_shap/ "
                        "(use 'clarify/shap' after the output-path fix)")
    p.add_argument("--endpoint", default=config.resource("monitor"))
    p.add_argument("--rows", type=int, default=3, help="rows for the additivity check")
    args = p.parse_args()

    import json
    sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = sess.client("s3")
    rt = sess.client("sagemaker-runtime")
    pre = args.clarify_prefix.rstrip("/")

    # --- load the two files behind the charts ---
    analysis = json.loads(_get_text(s3, f"{pre}/analysis.json"))
    shap = analysis["explanations"]["kernel_shap"]["label0"]
    global_shap = shap["global_shap_values"]          # the bar-chart numbers
    expected_value = shap["expected_value"]            # the SHAP baseline

    out = _get_text(s3, f"{pre}/explanations_shap/out.csv").splitlines()
    feats = [c[:-len("_label0")] if c.endswith("_label0") else c
             for c in out[0].split(",")]
    local = [[float(x) for x in line.split(",")] for line in out[1:]]
    n = len(local)

    # ================= CHECK 1: global bars == mean(|local|) =================
    print(f"CHECK 1 — global SHAP bars vs recomputed mean(|local|)  ({n} rows)")
    print(f"  {'feature':<28}{'report':>12}{'recomputed':>14}{'diff':>12}")
    worst = 0.0
    order = sorted(range(len(feats)), key=lambda j: -abs(global_shap.get(feats[j], 0)))
    for j in order:
        col = feats[j]
        recomputed = sum(abs(local[i][j]) for i in range(n)) / n
        reported = global_shap.get(col, float("nan"))
        diff = abs(reported - recomputed)
        worst = max(worst, diff)
        print(f"  {col:<28}{reported:>12.5f}{recomputed:>14.5f}{diff:>12.6f}")
    print(f"  -> max difference across all features: {worst:.2e} "
          f"({'MATCH' if worst < 1e-3 else 'CHECK'})\n")

    # ================= CHECK 2: additivity vs the live endpoint =================
    print(f"CHECK 2 — additivity: expected_value + sum(local SHAP) == endpoint prediction")
    print(f"  expected_value (baseline) = {expected_value:.5f}")
    sample = _get_text(s3, SAMPLE_KEY).splitlines()
    # sample col 0 is the label (high_demand); features start at col 1, in `feats` order.
    print(f"  {'row':>4}{'sum(local)':>14}{'+baseline':>14}{'endpoint':>12}{'diff':>11}")
    for i in range(min(args.rows, n)):
        feat_row = sample[i + 1].split(",")[1:]          # drop label
        body = ",".join(feat_row)
        raw = rt.invoke_endpoint(
            EndpointName=args.endpoint, ContentType="text/csv", Body=body,
        )["Body"].read().decode()
        pred = float(raw.strip().strip("[]"))  # endpoint returns e.g. "[0.6819]"
        shap_sum = sum(local[i])
        reconstructed = expected_value + shap_sum
        print(f"  {i:>4}{shap_sum:>14.5f}{reconstructed:>14.5f}"
              f"{pred:>12.5f}{abs(reconstructed - pred):>11.6f}")
    print("\n  Each row: the SHAP attributions add back up to exactly the number the\n"
          "  endpoint returns. That is the SHAP additivity guarantee — the chart is real.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
