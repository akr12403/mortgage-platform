#!/usr/bin/env bash
# M8 Task 8.3: deploy the document processor Lambda and wire it to the documents bucket (idempotent).
#   aws login --profile capstone-dev --region us-east-2
#   bash scripts/aws/lambda-deploy.sh
#   bash scripts/aws/lambda-verify.sh     # upload a valid + an invalid file, show metadata items and log lines
# Creates/updates, in order:
#   1. DynamoDB table CapstoneMortgageDocumentMetadata-dev (on-demand, TTL on expiresAt)
#   2. log group /aws/lambda/capstone-mortgage-doc-processor-dev (7-day retention; the role cannot create it)
#   3. the function: zip of infrastructure/aws/lambda/doc_processor/handler.py, python3.14, arm64, 256 MB, 30 s,
#      execution role lambda-doc-processor-role (Task 8.1)
#   4. permission for S3 to invoke it (this bucket, this account only) + the bucket notification
#      (s3:ObjectCreated:* on mortgages/)
#   5. CloudWatch alarm on the function's Errors metric (stub: no action attached; see the design doc)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session
R="$AWS_SANDBOX_REGION"
SRC="$AWS_INFRA_DIR/lambda/doc_processor"
OUT="$RENDER_DIR/lambda"; mkdir -p "$OUT"
LOG_GROUP="/aws/lambda/$LAMBDA_FUNCTION"
ALARM="$LAMBDA_FUNCTION-errors"
TAGS_KV="Project=$TAG_PROJECT,Environment=$TAG_ENVIRONMENT,Team=$TAG_TEAM"

log "1. DynamoDB table $DOC_METADATA_TABLE"
if aws_sb dynamodb describe-table --table-name "$DOC_METADATA_TABLE" >/dev/null 2>&1; then
  ok "exists"
else
  render "$AWS_INFRA_DIR/dynamodb/document-metadata-table.json" "$OUT/table.json"
  aws_sb dynamodb create-table --cli-input-json "file://$OUT/table.json" >/dev/null
  aws_sb dynamodb wait table-exists --table-name "$DOC_METADATA_TABLE"
  ok "created (on-demand, PK mortgageExternalId + SK s3Key)"
fi
ttl=$(aws_sb dynamodb describe-time-to-live --table-name "$DOC_METADATA_TABLE" --query 'TimeToLiveDescription.TimeToLiveStatus' --output text)
if [ "$ttl" != "ENABLED" ] && [ "$ttl" != "ENABLING" ]; then
  aws_sb dynamodb update-time-to-live --table-name "$DOC_METADATA_TABLE" \
    --time-to-live-specification "Enabled=true,AttributeName=expiresAt" >/dev/null
fi
ok "TTL on expiresAt"

log "2. Log group $LOG_GROUP"
if [ "$(aws_sb logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --query "length(logGroups[?logGroupName=='$LOG_GROUP'])" --output text)" = "0" ]; then
  aws_sb logs create-log-group --log-group-name "$LOG_GROUP" --tags "$TAGS_KV"
  ok "created"
fi
aws_sb logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 7
ok "retention 7 days"

log "3. Function $LAMBDA_FUNCTION"
python3 - "$SRC/handler.py" "$OUT/doc-processor.zip" <<'PY'
import sys, zipfile
src, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    info = zipfile.ZipInfo("handler.py", date_time=(2026, 1, 1, 0, 0, 0))   # fixed timestamp: same code, same zip
    info.external_attr = 0o644 << 16                                       # readable by the Lambda runtime user
    z.writestr(info, open(src, "rb").read(), zipfile.ZIP_DEFLATED)
PY
ok "packaged handler.py -> ${OUT#$REPO_ROOT/}/doc-processor.zip ($(wc -c < "$OUT/doc-processor.zip" | tr -d ' ') bytes)"
ROLE_ARN=$(aws_sb iam get-role --role-name lambda-doc-processor-role --query Role.Arn --output text)
ENVVARS="Variables={DOC_METADATA_TABLE=$DOC_METADATA_TABLE,DOCS_UPLOAD_PREFIX=$DOCS_UPLOAD_PREFIX,MAX_DOCUMENT_BYTES=10485760,METADATA_RETENTION_DAYS=30}"
if aws_sb lambda get-function --function-name "$LAMBDA_FUNCTION" >/dev/null 2>&1; then
  aws_sb lambda update-function-code --function-name "$LAMBDA_FUNCTION" --zip-file "fileb://$OUT/doc-processor.zip" >/dev/null
  aws_sb lambda wait function-updated-v2 --function-name "$LAMBDA_FUNCTION"
  aws_sb lambda update-function-configuration --function-name "$LAMBDA_FUNCTION" --role "$ROLE_ARN" \
    --runtime python3.14 --handler handler.lambda_handler --timeout 30 --memory-size 256 \
    --environment "$ENVVARS" --logging-config "LogFormat=Text,LogGroup=$LOG_GROUP" >/dev/null
  aws_sb lambda wait function-updated-v2 --function-name "$LAMBDA_FUNCTION"
  ok "code and configuration updated"
else
  # A role created moments ago can take a few seconds before Lambda may assume it: retry briefly.
  for attempt in 1 2 3 4 5 6; do
    if out=$(aws_sb lambda create-function --function-name "$LAMBDA_FUNCTION" --role "$ROLE_ARN" \
        --runtime python3.14 --architectures arm64 --handler handler.lambda_handler --timeout 30 --memory-size 256 \
        --zip-file "fileb://$OUT/doc-processor.zip" --environment "$ENVVARS" \
        --logging-config "LogFormat=Text,LogGroup=$LOG_GROUP" \
        --description "M8: validate uploaded mortgage documents, write metadata to DynamoDB" \
        --tags "$TAGS_KV" 2>&1); then break; fi
    printf '%s' "$out" | grep -q 'cannot be assumed' || die "$(printf '%s' "$out" | tail -1)"
    warn "role not assumable yet (attempt $attempt), waiting 10 s"; sleep 10
  done
  aws_sb lambda wait function-active-v2 --function-name "$LAMBDA_FUNCTION"
  ok "created (python3.14, arm64, 256 MB, 30 s, role lambda-doc-processor-role)"
fi
FN_ARN=$(aws_sb lambda get-function --function-name "$LAMBDA_FUNCTION" --query Configuration.FunctionArn --output text)

log "4. S3 trigger s3://$DOCS_BUCKET/$DOCS_UPLOAD_PREFIX -> $LAMBDA_FUNCTION"
aws_sb lambda remove-permission --function-name "$LAMBDA_FUNCTION" --statement-id s3-docs-bucket-invoke >/dev/null 2>&1 || true
aws_sb lambda add-permission --function-name "$LAMBDA_FUNCTION" --statement-id s3-docs-bucket-invoke \
  --action lambda:InvokeFunction --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::$DOCS_BUCKET" --source-account "$ACCOUNT_ID" >/dev/null
ok "invoke permission: principal s3.amazonaws.com, source bucket $DOCS_BUCKET, source account only"
NOTIF=$(python3 -c 'import json,sys; print(json.dumps({"LambdaFunctionConfigurations":[{"Id":"doc-processor-on-upload","LambdaFunctionArn":sys.argv[1],"Events":["s3:ObjectCreated:*"],"Filter":{"Key":{"FilterRules":[{"Name":"prefix","Value":sys.argv[2]}]}}}]}))' "$FN_ARN" "$DOCS_UPLOAD_PREFIX")
aws_sb s3api put-bucket-notification-configuration --bucket "$DOCS_BUCKET" --notification-configuration "$NOTIF"
ok "bucket notification: s3:ObjectCreated:* with prefix $DOCS_UPLOAD_PREFIX"

log "5. Error alarm $ALARM (stub)"
aws_sb cloudwatch put-metric-alarm --alarm-name "$ALARM" \
  --alarm-description "M8 stub: document Lambda failed at least once in 5 minutes. No action attached; runbook: docs/architecture/aws-document-lambda.md#error-alarm" \
  --namespace AWS/Lambda --metric-name Errors --dimensions "Name=FunctionName,Value=$LAMBDA_FUNCTION" \
  --statistic Sum --period 300 --evaluation-periods 1 --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching \
  --tags "Key=Project,Value=$TAG_PROJECT" "Key=Environment,Value=$TAG_ENVIRONMENT" "Key=Team,Value=$TAG_TEAM"
ok "Errors >= 1 in 5 min -> ALARM (no action yet)"

printf '\n\033[1;32mLambda deployed.\033[0m Next: bash scripts/aws/lambda-verify.sh\n'
