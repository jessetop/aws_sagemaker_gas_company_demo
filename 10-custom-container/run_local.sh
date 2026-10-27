#!/usr/bin/env bash
# Run the SAME container on your laptop — no AWS, no SageMaker. This mounts the
# bundled sample data into the exact paths SageMaker would use, then runs `train`.
# Proves the container is self-contained before you scale it out.
#
#   ./run_local.sh
set -euo pipefail
# On Git Bash for Windows, stop MSYS from rewriting the container path
# (/opt/ml/...) into a Windows path. No-op on Linux/Mac.
export MSYS_NO_PATHCONV=1
here="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${IMAGE:-roi-smdemo-custom-train:latest}"

mkdir -p "$here/local-output/model" "$here/local-output/output"

echo "== running $IMAGE locally, SageMaker-style paths =="
echo "   input : $here/sample-data       -> /opt/ml/input/data"
echo "   model : $here/local-output/model -> /opt/ml/model"
docker run --rm \
  -v "$here/sample-data:/opt/ml/input/data" \
  -v "$here/local-output/model:/opt/ml/model" \
  -v "$here/local-output/output:/opt/ml/output" \
  "$IMAGE" train

echo ""
echo "Trained locally. Model artifact:"
ls -la "$here/local-output/model"
