#!/usr/bin/env bash
# M8 Tasks 8.2/8.4: run analytics-service against real S3 (documents) and DynamoDB (lookup) with
# mortgage-analytics-role credentials.
#   aws login --profile capstone-dev --region us-east-2
#   bash scripts/aws/compose-aws-up.sh            # (re)creates analytics-service; the rest of the stack as usual
#   docker compose up -d analytics-service        # back to the LocalStack-only setup
# No access keys: the developer session assumes the role for 1 hour (role chaining maximum) and the temporary
# credentials go to docker compose through this process's environment only. Nothing is written to disk.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session

log "Assume mortgage-analytics-role (1 hour)"
ROLE_ARN=$(aws_sb iam get-role --role-name mortgage-analytics-role --query Role.Arn --output text)
read -r AK SK ST EXP < <(aws_sb sts assume-role --role-arn "$ROLE_ARN" --role-session-name analytics-service-local \
  --duration-seconds 3600 --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken,Expiration]' --output text)
[ -n "${ST:-}" ] || die "assume-role failed (see the error above); run iam-apply.sh if the role is missing"
export M8_ANALYTICS_AWS_ACCESS_KEY_ID="$AK" M8_ANALYTICS_AWS_SECRET_ACCESS_KEY="$SK" M8_ANALYTICS_AWS_SESSION_TOKEN="$ST"
export M8_AWS_REGION="$AWS_SANDBOX_REGION" M8_DOCS_BUCKET="$DOCS_BUCKET" M8_LOOKUP_TABLE="$LOOKUP_TABLE"
ok "credentials valid until $EXP"

log "Start analytics-service with S3 -> s3://$DOCS_BUCKET, DynamoDB -> $LOOKUP_TABLE ($AWS_SANDBOX_REGION)"
cd "$REPO_ROOT"
docker compose ps --status running --services 2>/dev/null | grep -qx postgres \
  || die "start the local stack first: docker compose up --build -d"
docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d --force-recreate --no-deps analytics-service
ok "analytics-service recreated; SQS still on LocalStack, S3 + DynamoDB ($LOOKUP_TABLE) on AWS"
printf '\nUpload a document as usual (POST :8000/api/v1/documents/upload); it lands in s3://%s/%s<id>/.\n' \
  "$DOCS_BUCKET" "$DOCS_UPLOAD_PREFIX"
