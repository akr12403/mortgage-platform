#!/usr/bin/env bash
# M8 Task 8.3: prove the upload -> Lambda -> DynamoDB + CloudWatch Logs flow on the real sandbox.
#   bash scripts/aws/lambda-verify.sh            # uploads 2 synthetic files as mortgage-analytics-role, then cleans up
#   KEEP=1 bash scripts/aws/lambda-verify.sh     # keep the test objects and items (e.g. to show them in the demo)
# Expected: the real PDF -> VALIDATED; text pretending to be a PDF -> REJECTED [MAGIC_BYTES_MISMATCH]; both items
# carry the upload's correlation id, and the function's JSON log lines show the same id.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session
R="$AWS_SANDBOX_REGION"
LOG_GROUP="/aws/lambda/$LAMBDA_FUNCTION"
fails=0
pass_() { printf '    \033[1;32mPASS\033[0m %s\n' "$*"; }
fail_() { printf '    \033[1;31mFAIL\033[0m %s\n' "$*"; fails=$((fails + 1)); }

aws_sb lambda get-function --function-name "$LAMBDA_FUNCTION" >/dev/null 2>&1 || die "run bash scripts/aws/lambda-deploy.sh first"

log "Upload 2 synthetic documents as mortgage-analytics-role"
ROLE_ARN=$(aws_sb iam get-role --role-name mortgage-analytics-role --query Role.Arn --output text)
CREDS=$(aws_sb sts assume-role --role-arn "$ROLE_ARN" --role-session-name m8-lambda-verify --duration-seconds 900 \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)
as_role() {
  env -u AWS_PROFILE AWS_ACCESS_KEY_ID="$(printf '%s' "$CREDS" | cut -f1)" \
    AWS_SECRET_ACCESS_KEY="$(printf '%s' "$CREDS" | cut -f2)" AWS_SESSION_TOKEN="$(printf '%s' "$CREDS" | cut -f3)" \
    aws --region "$R" "$@"
}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
CID="m8-lambda-verify-$STAMP"
START_MS=$(( $(date +%s) * 1000 - 5000 ))
WORK="$RENDER_DIR/lambda-verify"; mkdir -p "$WORK"
printf '%%PDF-1.4\n%% synthetic M8 test document, no borrower data\n%%%%EOF\n' > "$WORK/valid.pdf"
printf 'plain text pretending to be a PDF\n' > "$WORK/fake.pdf"
uuid() { python3 -c 'import uuid; print(uuid.uuid4())'; }
VALID_KEY="${DOCS_UPLOAD_PREFIX}MTG-0000/$(uuid)-verify-valid.pdf"
FAKE_KEY="${DOCS_UPLOAD_PREFIX}MTG-0000/$(uuid)-verify-fake.pdf"
for pair in "$VALID_KEY|$WORK/valid.pdf" "$FAKE_KEY|$WORK/fake.pdf"; do
  key="${pair%%|*}"; file="${pair#*|}"
  as_role s3api put-object --bucket "$DOCS_BUCKET" --key "$key" --body "$file" --content-type application/pdf \
    --metadata "correlation-id=$CID,document-type=TEST" >/dev/null
  ok "uploaded s3://$DOCS_BUCKET/$key"
done

log "Wait for the Lambda to write the metadata items (up to 60 s)"
get_item() {
  aws_sb dynamodb get-item --table-name "$DOC_METADATA_TABLE" --consistent-read \
    --key "{\"mortgageExternalId\":{\"S\":\"MTG-0000\"},\"s3Key\":{\"S\":\"$1\"}}" \
    --query 'Item.[status.S, join(`,`, rejectReasons.SS || `[]`), correlationId.S, contentType.S, sizeBytes.N, serverSideEncryption.S]' \
    --output text
}
for key in "$VALID_KEY" "$FAKE_KEY"; do
  item=""
  for _ in $(seq 1 20); do
    item=$(get_item "$key")
    [ -n "$item" ] && [ "$item" != "None" ] && break
    sleep 3
  done
  case "$key" in *valid*) expect="VALIDATED" ;; *) expect="REJECTED" ;; esac
  status=$(printf '%s' "$item" | cut -f1); reasons=$(printf '%s' "$item" | cut -f2); cid=$(printf '%s' "$item" | cut -f3)
  if [ "$status" = "$expect" ] && [ "$cid" = "$CID" ]; then
    pass_ "$(basename "$key"): $status${reasons:+ [$reasons]}  correlationId=$cid  $(printf '%s' "$item" | cut -f4) $(printf '%s' "$item" | cut -f5) bytes $(printf '%s' "$item" | cut -f6)"
  else
    fail_ "$(basename "$key"): expected $expect with correlationId $CID, got '${item:-no item after 60 s}'"
  fi
done
case "$(get_item "$FAKE_KEY" | cut -f2)" in *MAGIC_BYTES_MISMATCH*) pass_ "fake PDF rejected for MAGIC_BYTES_MISMATCH" ;; *) fail_ "fake PDF reason missing" ;; esac

log "CloudWatch Logs: the function's structured JSON lines for correlationId $CID"
lines=""
for _ in $(seq 1 10); do
  lines=$(aws_sb logs filter-log-events --log-group-name "$LOG_GROUP" --start-time "$START_MS" \
    --filter-pattern "{ \$.correlationId = \"$CID\" }" --query 'events[].message' --output text 2>/dev/null || true)
  [ "$(printf '%s' "$lines" | grep -c '"service"' || true)" -ge 2 ] && break
  sleep 3
done
if [ "$(printf '%s' "$lines" | tr '\t' '\n' | grep -c '"service"' || true)" -ge 2 ]; then
  printf '%s\n' "$lines" | tr '\t' '\n' | grep '"service"' | sed 's/^/      /'
  pass_ "2 JSON log lines found by a CloudWatch Logs filter on correlationId"
else
  fail_ "log lines not found yet (logs can lag ~10 s): aws logs tail $LOG_GROUP --since 5m --profile $AWS_SANDBOX_PROFILE"
fi

log "Error alarm"
state=$(aws_sb cloudwatch describe-alarms --alarm-names "$LAMBDA_FUNCTION-errors" --query 'MetricAlarms[0].StateValue' --output text)
case "$state" in OK|INSUFFICIENT_DATA) pass_ "$LAMBDA_FUNCTION-errors exists, state $state (no failures)" ;; *) fail_ "alarm state '$state'" ;; esac

if [ "${KEEP:-0}" != "1" ]; then
  log "Clean up (developer session)"
  for key in "$VALID_KEY" "$FAKE_KEY"; do
    aws_sb s3api delete-object --bucket "$DOCS_BUCKET" --key "$key" >/dev/null
    aws_sb dynamodb delete-item --table-name "$DOC_METADATA_TABLE" \
      --key "{\"mortgageExternalId\":{\"S\":\"MTG-0000\"},\"s3Key\":{\"S\":\"$key\"}}"
  done
  ok "test objects and metadata items deleted"
fi
rm -rf "$WORK"

[ "$fails" = 0 ] || die "$fails check(s) failed"
printf '\n\033[1;32mLambda workflow verified.\033[0m Upload -> validate -> DynamoDB item -> JSON log line, traced by correlationId.\n'
