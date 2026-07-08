#!/usr/bin/env bash
# Immediately kill running SageMaker Canvas apps (the ~$50/day biller).
# Scans the given regions, lists apps, and deletes Canvas sessions on demand.
#
#   ./cleanup/kill_canvas.sh                    # kill Canvas in us-east-1 + us-east-2
#   ALL=1 ./cleanup/kill_canvas.sh              # also kill JupyterLab/KernelGateway
#   REGIONS="us-east-1" ./cleanup/kill_canvas.sh
#   DRY_RUN=1 ./cleanup/kill_canvas.sh          # list only, delete nothing
set -uo pipefail

PROFILE="${PROFILE:-roitraining}"
REGIONS="${REGIONS:-us-east-1 us-east-2}"
if [[ "${ALL:-0}" == "1" ]]; then
  KILL_TYPES="Canvas JupyterLab KernelGateway RStudioServerPro RSession TensorBoard CodeEditor"
else
  KILL_TYPES="Canvas"
fi

is_kill_type() { [[ " $KILL_TYPES " == *" $1 "* ]]; }

for r in $REGIONS; do
  echo "== Region $r : scanning apps =="
  for d in $(aws sagemaker list-domains --profile "$PROFILE" --region "$r" --query "Domains[].DomainId" --output text 2>/dev/null); do
    apps=$(aws sagemaker list-apps --domain-id-equals "$d" --profile "$PROFILE" --region "$r" \
      --query "Apps[?Status!='Deleted' && Status!='Deleting'].[AppType,AppName,Status,UserProfileName,SpaceName]" \
      --output text 2>/dev/null)
    [[ -z "$apps" ]] && continue
    while IFS=$'\t' read -r atype aname status uprofile space; do
      [[ -z "$atype" ]] && continue
      is_kill_type "$atype" || continue
      if [[ "$uprofile" != "None" && -n "$uprofile" ]]; then scope=(--user-profile-name "$uprofile"); else scope=(--space-name "$space"); fi
      label="$atype/$aname [$status] in $d"
      if [[ "${DRY_RUN:-0}" == "1" ]]; then echo "  WOULD DELETE $label"; continue; fi
      echo "  deleting $label"
      aws sagemaker delete-app --domain-id "$d" --app-type "$atype" --app-name "$aname" \
        "${scope[@]}" --profile "$PROFILE" --region "$r" 2>/dev/null
    done <<< "$apps"
  done
done

echo "Done. Canvas apps take a minute or two to fully transition to Deleted."
