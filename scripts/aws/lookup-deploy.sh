#!/usr/bin/env bash
# M8 Task 8.4: create the DynamoDB mortgage lookup table (idempotent).
#   aws login --profile capstone-dev --region us-east-2
#   bash scripts/aws/lookup-deploy.sh     # table CapstoneMortgageLookup-dev, PK mortgageExternalId, on-demand
#   bash scripts/aws/lookup-load.sh       # bulk-load it from PostgreSQL (local stack must be running)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session

log "DynamoDB table $LOOKUP_TABLE"
if aws_sb dynamodb describe-table --table-name "$LOOKUP_TABLE" >/dev/null 2>&1; then
  ok "exists"
else
  render "$AWS_INFRA_DIR/dynamodb/mortgage-lookup-table.json" "$RENDER_DIR/dynamodb/lookup-table.json"
  aws_sb dynamodb create-table --cli-input-json "file://$RENDER_DIR/dynamodb/lookup-table.json" >/dev/null
  aws_sb dynamodb wait table-exists --table-name "$LOOKUP_TABLE"
  ok "created"
fi
aws_sb dynamodb describe-table --table-name "$LOOKUP_TABLE" --output text \
  --query 'Table.[TableStatus, KeySchema[0].AttributeName, KeySchema[0].KeyType, BillingModeSummary.BillingMode, ItemCount]' \
  | awk '{printf "  status %s  key %s (%s)  billing %s  items %s (refreshed ~6 h by AWS)\n", $1, $2, $3, $4, $5}'

printf '\n\033[1;32mLookup table ready.\033[0m Next: bash scripts/aws/lookup-load.sh\n'
