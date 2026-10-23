#!/usr/bin/env bash
# Build the custom training image and push it to ECR.
# Teaching flow (run each step live): build -> ensure repo -> login -> tag -> push.
#
#   ./build_and_push.sh
#   REPO=my-repo TAG=v1 ./build_and_push.sh
set -euo pipefail

ACCOUNT="${ACCOUNT:-029331796573}"
REGION="${REGION:-us-east-1}"
PROFILE="${PROFILE:-roitraining}"
REPO="${REPO:-roi-smdemo-custom-train}"
TAG="${TAG:-latest}"

here="$(cd "$(dirname "$0")" && pwd)"
IMAGE="$REPO:$TAG"
ECR="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
ECR_IMAGE="$ECR/$IMAGE"

echo "== 1/5 build image: $IMAGE =="
docker build -t "$IMAGE" "$here/container"

echo "== 2/5 ensure ECR repository exists: $REPO =="
aws ecr describe-repositories --repository-names "$REPO" --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --profile "$PROFILE" --region "$REGION" >/dev/null
echo "   repo: $ECR/$REPO"

echo "== 3/5 authenticate Docker to ECR =="
aws ecr get-login-password --profile "$PROFILE" --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR"

echo "== 4/5 tag for ECR =="
docker tag "$IMAGE" "$ECR_IMAGE"

echo "== 5/5 push to ECR =="
docker push "$ECR_IMAGE"

echo ""
echo "DONE. Image now in ECR:"
echo "  $ECR_IMAGE"
echo "See it:   aws ecr describe-images --repository-name $REPO --profile $PROFILE --region $REGION"
echo "Run on SageMaker:"
echo "  python launch_sagemaker_training.py --image-uri $ECR_IMAGE"
