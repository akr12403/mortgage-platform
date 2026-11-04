#!/usr/bin/env bash
# M8 teardown: delete what the M8 scripts created in the AWS sandbox (cost control; the repo keeps everything).
#   bash scripts/aws/teardown.sh          # lists what will be deleted and asks for confirmation
#   bash scripts/aws/teardown.sh --yes    # no prompt
# Grows with each task: 8.1 IAM roles, 8.2 S3 buckets (emptied first), 8.3 Lambda + its log group, alarm, metadata
# table and S3 trigger, 8.4 DynamoDB lookup table, 8.5 Glue job and its log groups, 8.6 pipeline alert rule + log group.
# Only names from infrastructure/aws/ are touched; anything else in the account is left alone.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

YES=0; [ "${1:-}" = "--yes" ] && YES=1

log "Session"
require_session

log "Will delete"
LOG_GROUP="/aws/lambda/$LAMBDA_FUNCTION"; ALARM="$LAMBDA_FUNCTION-errors"
HAS_FN=0; HAS_LOGS=0; HAS_ALARM=0; HAS_TABLE=0
aws_sb lambda get-function --function-name "$LAMBDA_FUNCTION" >/dev/null 2>&1 && { HAS_FN=1; printf '  Lambda %s (and the S3 trigger)\n' "$LAMBDA_FUNCTION"; }
[ "$(aws_sb logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --query "length(logGroups[?logGroupName=='$LOG_GROUP'])" --output text)" != "0" ] \
  && { HAS_LOGS=1; printf '  log group %s\n' "$LOG_GROUP"; }
[ "$(aws_sb cloudwatch describe-alarms --alarm-names "$ALARM" --query 'length(MetricAlarms)' --output text)" != "0" ] \
  && { HAS_ALARM=1; printf '  alarm %s\n' "$ALARM"; }
aws_sb dynamodb describe-table --table-name "$DOC_METADATA_TABLE" >/dev/null 2>&1 && { HAS_TABLE=1; printf '  DynamoDB table %s\n' "$DOC_METADATA_TABLE"; }
HAS_GLUE=0
aws_sb glue get-job --job-name "$GLUE_JOB" >/dev/null 2>&1 && { HAS_GLUE=1; printf '  Glue job %s (+ /aws-glue/python-jobs/* log groups)\n' "$GLUE_JOB"; }
HAS_LOOKUP=0
aws_sb dynamodb describe-table --table-name "$LOOKUP_TABLE" >/dev/null 2>&1 && { HAS_LOOKUP=1; printf '  DynamoDB table %s\n' "$LOOKUP_TABLE"; }
BUCKETS=()
for bucket in "$DOCS_BUCKET" "$ANALYTICS_BUCKET"; do
  if aws_sb s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
    BUCKETS+=("$bucket")
    printf '  S3 bucket %s (%s objects)\n' "$bucket" \
      "$(aws_sb s3api list-objects-v2 --bucket "$bucket" --query 'KeyCount' --output text)"
  fi
done
ROLE_NAMES=()
while IFS='|' read -r name _ <&3; do
  if aws_sb iam get-role --role-name "$name" >/dev/null 2>&1; then ROLE_NAMES+=("$name"); printf '  IAM role %s\n' "$name"; fi
done 3< <(roles)
[ $((HAS_FN + HAS_LOGS + HAS_ALARM + HAS_TABLE + HAS_LOOKUP + HAS_GLUE + ${#BUCKETS[@]} + ${#ROLE_NAMES[@]})) -gt 0 ] || { ok "nothing to delete"; exit 0; }

if [ "$YES" != 1 ]; then
  read -r -p "  Delete these from account $ACCOUNT_ID? Type 'delete' to confirm: " answer
  [ "$answer" = "delete" ] || die "aborted, nothing deleted"
fi

if [ $((HAS_FN + HAS_LOGS + HAS_ALARM + HAS_TABLE)) -gt 0 ]; then
  log "Document Lambda (Task 8.3)"
  if [ "$HAS_FN" = 1 ]; then
    aws_sb s3api head-bucket --bucket "$DOCS_BUCKET" >/dev/null 2>&1 \
      && aws_sb s3api put-bucket-notification-configuration --bucket "$DOCS_BUCKET" --notification-configuration '{}'
    aws_sb lambda delete-function --function-name "$LAMBDA_FUNCTION"; ok "deleted Lambda $LAMBDA_FUNCTION and the S3 trigger"
  fi
  [ "$HAS_ALARM" = 1 ] && { aws_sb cloudwatch delete-alarms --alarm-names "$ALARM"; ok "deleted alarm $ALARM"; }
  [ "$HAS_LOGS" = 1 ] && { aws_sb logs delete-log-group --log-group-name "$LOG_GROUP"; ok "deleted log group $LOG_GROUP"; }
  [ "$HAS_TABLE" = 1 ] && { aws_sb dynamodb delete-table --table-name "$DOC_METADATA_TABLE" >/dev/null; ok "deleted table $DOC_METADATA_TABLE"; }
fi

if [ "$HAS_GLUE" = 1 ]; then
  log "Data pipeline (Task 8.5)"
  if aws_sb events describe-rule --name "$GLUE_JOB-failed" >/dev/null 2>&1; then
    aws_sb events remove-targets --rule "$GLUE_JOB-failed" --ids pipeline-alert-log >/dev/null
    aws_sb events delete-rule --name "$GLUE_JOB-failed"; ok "deleted EventBridge rule $GLUE_JOB-failed"
  fi
  aws_sb logs delete-resource-policy --policy-name capstone-mortgage-pipeline-alerts 2>/dev/null || true
  aws_sb logs delete-log-group --log-group-name "$PIPELINE_ALERT_LOG_GROUP" 2>/dev/null && ok "deleted log group $PIPELINE_ALERT_LOG_GROUP" || true
  aws_sb glue delete-job --job-name "$GLUE_JOB" >/dev/null; ok "deleted Glue job $GLUE_JOB"
  for group in /aws-glue/python-jobs/output /aws-glue/python-jobs/error; do
    aws_sb logs delete-log-group --log-group-name "$group" 2>/dev/null && ok "deleted log group $group" || true
  done
fi

if [ "$HAS_LOOKUP" = 1 ]; then
  log "Mortgage lookup (Task 8.4)"
  aws_sb dynamodb delete-table --table-name "$LOOKUP_TABLE" >/dev/null; ok "deleted table $LOOKUP_TABLE"
fi

if [ ${#BUCKETS[@]} -gt 0 ]; then
  log "S3 buckets"
  for bucket in "${BUCKETS[@]}"; do
    aws_sb s3 rm "s3://$bucket" --recursive --only-show-errors
    aws_sb s3api delete-bucket --bucket "$bucket"
    ok "emptied and deleted $bucket"
  done
fi

if [ ${#ROLE_NAMES[@]} -gt 0 ]; then
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
fi

printf '\n\033[1;32mTeardown complete.\033[0m Re-create with iam-apply.sh, s3-apply.sh, lambda-deploy.sh, lookup-deploy.sh, pipeline-deploy.sh.\n'
