#!/usr/bin/env bash
# Copy the project dataset from the old us-east-2 bucket into the new us-east-1
# bucket (same account => server-side S3 copy). Run AFTER `terraform apply`.
#
#   ./shared/sync_data_to_us_east_1.sh
#   RAW_ONLY=1 ./shared/sync_data_to_us_east_1.sh
#   DRY_RUN=1  ./shared/sync_data_to_us_east_1.sh
set -euo pipefail

PROFILE="${PROFILE:-roitraining}"
SOURCE="${SOURCE:-roi-smdemo-029331796573-us-east-2}"
DEST="${DEST:-roi-smdemo-029331796573-us-east-1}"

if ! aws s3api head-bucket --bucket "$DEST" --profile "$PROFILE" 2>/dev/null; then
  echo "Destination bucket s3://$DEST not found. Run 'terraform apply' first." >&2
  exit 1
fi

prefix=""
[[ "${RAW_ONLY:-0}" == "1" ]] && prefix="raw/"
extra=()
[[ "${DRY_RUN:-0}" == "1" ]] && extra+=(--dryrun)

echo "== sync s3://$SOURCE/$prefix -> s3://$DEST/$prefix =="
aws s3 sync "s3://$SOURCE/$prefix" "s3://$DEST/$prefix" \
  --profile "$PROFILE" --source-region us-east-2 --region us-east-1 "${extra[@]}"

echo "Done. Verify: aws s3 ls s3://$DEST/ --profile $PROFILE"
