#!/usr/bin/env bash
# M8 teardown: delete what the M8 scripts created in the AWS sandbox (cost control; the repo keeps everything).
#   bash scripts/aws/teardown.sh          # lists what will be deleted and asks for confirmation
#   bash scripts/aws/teardown.sh --yes    # no prompt
# Grows with each task (8.1 IAM roles today; S3, Lambda, DynamoDB, Glue, SQS/SNS as they are added).
# Only names from infrastructure/aws/ are touched; anything else in the account is left alone.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

YES=0; [ "${1:-}" = "--yes" ] && YES=1

log "Session"
require_session

log "Will delete"
ROLE_NAMES=()
while IFS='|' read -r name _ <&3; do
  if aws_sb iam get-role --role-name "$name" >/dev/null 2>&1; then ROLE_NAMES+=("$name"); printf '  IAM role %s\n' "$name"; fi
done 3< <(roles)
[ ${#ROLE_NAMES[@]} -gt 0 ] || { ok "nothing to delete"; exit 0; }

if [ "$YES" != 1 ]; then
  read -r -p "  Delete these from account $ACCOUNT_ID? Type 'delete' to confirm: " answer
  [ "$answer" = "delete" ] || die "aborted, nothing deleted"
fi

log "IAM roles"
for name in "${ROLE_NAMES[@]}"; do
  for p in $(aws_sb iam list-role-policies --role-name "$name" --query 'PolicyNames' --output text); do
    aws_sb iam delete-role-policy --role-name "$name" --policy-name "$p"
  done
  for arn in $(aws_sb iam list-attached-role-policies --role-name "$name" --query 'AttachedPolicies[].PolicyArn' --output text); do
    aws_sb iam detach-role-policy --role-name "$name" --policy-arn "$arn"
  done
  aws_sb iam delete-role --role-name "$name"
  ok "deleted $name"
done

printf '\n\033[1;32mTeardown complete.\033[0m Re-create any time with bash scripts/aws/iam-apply.sh\n'
