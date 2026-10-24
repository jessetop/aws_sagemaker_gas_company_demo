#!/usr/bin/env bash
# Tear down resources created by the SageMaker Unified Studio demo series.
# Safe to re-run. Only touches resources named/tagged for this demo.
#
#   ./cleanup.sh                  # delete jobs/apps/endpoints, keep bucket+role
#   ./cleanup.sh --include-bucket # also empty + delete the S3 bucket
#   ./cleanup.sh --include-role   # also delete the shared IAM role
#
# Account, region, bucket and the resource-name prefix are read from demo.env so
# this script can never drift away from what the demos actually created. That
# drift was a real bug: this file used to default to us-east-2 and hardcode the
# us-east-2 bucket after the series had been redeployed to us-east-1, so a
# post-class teardown silently deleted nothing and left billable resources up.
#
# Override with environment variables for a one-off run:
#   REGION=us-west-2 ./cleanup.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../demo.env"

# Read a key out of demo.env without sourcing it (values are plain, unquoted).
conf() {
  local key="$1" default="$2" val=""
  if [ -f "$ENV_FILE" ]; then
    val=$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" \
          | tail -1 | tr -d '"'"'"'' | tr -d '\r')
  fi
  printf '%s' "${val:-$default}"
}

[ -f "$ENV_FILE" ] || echo "WARNING: demo.env not found at $ENV_FILE - using built-in defaults." >&2

ACCOUNT="${ACCOUNT:-$(conf SMDEMO_ACCOUNT 029331796573)}"
PROFILE="${PROFILE:-$(conf SMDEMO_PROFILE roitraining)}"
REGION="${REGION:-$(conf SMDEMO_REGION us-east-1)}"
BUCKET="${BUCKET:-$(conf SMDEMO_BUCKET "roi-smdemo-${ACCOUNT}-${REGION}")}"
PREFIX="${PREFIX:-$(conf SMDEMO_PREFIX roi-smdemo-gas)}"
ROLE="roi-smdemo-exec-role"

INCLUDE_BUCKET=false; INCLUDE_ROLE=false
for a in "$@"; do
  [ "$a" = "--include-bucket" ] && INCLUDE_BUCKET=true
  [ "$a" = "--include-role" ] && INCLUDE_ROLE=true
done

# Say out loud what we are about to operate on. A teardown pointed at the wrong
# region is indistinguishable from a successful one unless you print this.
echo "== Teardown target =="
echo "   account : $ACCOUNT"
echo "   region  : $REGION"
echo "   profile : $PROFILE"
echo "   bucket  : $BUCKET"
echo "   prefix  : ${PREFIX}*"
echo

echo "== Deleting Glue job, crawler, and demo database =="
aws glue delete-job --job-name "${PREFIX}-visual-etl" --profile "$PROFILE" --region "$REGION" 2>/dev/null
aws glue delete-crawler --name "${PREFIX}-crawler" --profile "$PROFILE" --region "$REGION" 2>/dev/null
aws glue delete-database --name gas_demo --profile "$PROFILE" --region "$REGION" 2>/dev/null

echo "== Deleting Feature Store group =="
aws sagemaker delete-feature-group --feature-group-name "${PREFIX}-features" --profile "$PROFILE" --region "$REGION" 2>/dev/null

echo "== Deleting Pipeline, Model Registry, Experiment =="
aws sagemaker delete-pipeline --pipeline-name "${PREFIX}-pipeline" --profile "$PROFILE" --region "$REGION" 2>/dev/null
for pkg in $(aws sagemaker list-model-packages --model-package-group-name "${PREFIX}-models" --profile "$PROFILE" --region "$REGION" --query "ModelPackageSummaryList[].ModelPackageArn" --output text 2>/dev/null); do
  aws sagemaker delete-model-package --model-package-name "$pkg" --profile "$PROFILE" --region "$REGION" 2>/dev/null
done
aws sagemaker delete-model-package-group --model-package-group-name "${PREFIX}-models" --profile "$PROFILE" --region "$REGION" 2>/dev/null
aws sagemaker delete-model --model-name "${PREFIX}-model" --profile "$PROFILE" --region "$REGION" 2>/dev/null
aws sagemaker delete-experiment --experiment-name "${PREFIX}-experiment" --profile "$PROFILE" --region "$REGION" 2>/dev/null

echo "== Deleting MLflow tracking server + its teardown schedule =="
aws sagemaker delete-mlflow-tracking-server --tracking-server-name "${PREFIX}-mlflow" --profile "$PROFILE" --region "$REGION" 2>/dev/null
aws scheduler delete-schedule --name "${PREFIX}-mlflow-teardown" --profile "$PROFILE" --region "$REGION" 2>/dev/null

echo "== Stopping + deleting EMR Serverless applications =="
for a in $(aws emr-serverless list-applications --profile "$PROFILE" --region "$REGION" \
            --query "applications[?name=='${PREFIX}-emr'].id" --output text); do
  aws emr-serverless stop-application --application-id "$a" --profile "$PROFILE" --region "$REGION" 2>/dev/null
  aws emr-serverless delete-application --application-id "$a" --profile "$PROFILE" --region "$REGION" 2>/dev/null
  echo "  deleted app $a"
done

echo "== Deleting SageMaker endpoints (modules 3-7) =="
for e in $(aws sagemaker list-endpoints --profile "$PROFILE" --region "$REGION" \
            --query "Endpoints[?starts_with(EndpointName,'roi-smdemo')].EndpointName" --output text); do
  aws sagemaker delete-endpoint --endpoint-name "$e" --profile "$PROFILE" --region "$REGION" 2>/dev/null
  echo "  deleted endpoint $e"
done

if $INCLUDE_BUCKET; then
  echo "== Emptying + deleting bucket $BUCKET =="
  aws s3 rm "s3://$BUCKET" --recursive --only-show-errors --profile "$PROFILE"
  aws s3api delete-bucket --bucket "$BUCKET" --profile "$PROFILE" --region "$REGION" 2>/dev/null
else
  echo "== Keeping bucket; clearing derived data only =="
  for p in processed tmp logs; do
    aws s3 rm "s3://$BUCKET/$p/" --recursive --only-show-errors --profile "$PROFILE"
  done
fi

if $INCLUDE_ROLE; then
  echo "== Deleting shared IAM role $ROLE =="
  aws iam delete-role-policy --role-name "$ROLE" --policy-name demo-permissions --profile "$PROFILE" 2>/dev/null
  aws iam detach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSageMakerFullAccess --profile "$PROFILE" 2>/dev/null
  aws iam delete-role --role-name "$ROLE" --profile "$PROFILE" 2>/dev/null
fi

# ------------------------------------------------------- verification sweep
# Every delete above is silenced with 2>/dev/null so a re-run stays quiet, which
# also means a FAILED delete looks exactly like a successful one. So we now go
# back and look for the things that actually cost money if left running.
echo
echo "== Verifying: anything still billable in $REGION ? =="
leftover=()

for e in $(aws sagemaker list-endpoints --profile "$PROFILE" --region "$REGION" \
            --query "Endpoints[].EndpointName" --output text 2>/dev/null); do
  leftover+=("endpoint: $e")
done
for a in $(aws emr-serverless list-applications --profile "$PROFILE" --region "$REGION" \
            --query "applications[?state!='TERMINATED'].name" --output text 2>/dev/null); do
  leftover+=("emr-serverless: $a")
done
for m in $(aws sagemaker list-mlflow-tracking-servers --profile "$PROFILE" --region "$REGION" \
            --query "TrackingServerSummaries[].TrackingServerName" --output text 2>/dev/null); do
  leftover+=("mlflow-server: $m")
done
# Studio / Unified Studio spaces are the classic overnight bill.
for a in $(aws sagemaker list-apps --profile "$PROFILE" --region "$REGION" \
            --query "Apps[?Status=='InService'].AppName" --output text 2>/dev/null); do
  leftover+=("studio app InService: $a")
done

if [ "${#leftover[@]}" -gt 0 ]; then
  echo "STILL RUNNING - these bill until removed:"
  for l in "${leftover[@]}"; do echo "   ! $l"; done
  echo
  echo "Cleanup finished with leftovers (see above)."
  exit 1
fi

echo "   nothing billable found."
echo
echo "Cleanup complete."
