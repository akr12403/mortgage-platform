#!/usr/bin/env bash
# M8 Task 8.4: bulk-load CapstoneMortgageLookup-dev from the local PostgreSQL, as mortgage-analytics-role.
#   docker compose up --build -d          # local stack running (PostgreSQL with the seed data)
#   bash scripts/aws/lookup-load.sh
# Runs `python -m src.services.lookup_load` in a one-off analytics-service container (same image, same DB settings)
# with 15-minute role credentials passed through the environment only, then checks the item count and reads one
# item back as the developer.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session
cd "$REPO_ROOT"
docker compose ps --status running --services 2>/dev/null | grep -qx postgres \
  || die "start the local stack first: docker compose up --build -d"
aws_sb dynamodb describe-table --table-name "$LOOKUP_TABLE" >/dev/null 2>&1 || die "run bash scripts/aws/lookup-deploy.sh first"

log "Assume mortgage-analytics-role (15 min)"
ROLE_ARN=$(aws_sb iam get-role --role-name mortgage-analytics-role --query Role.Arn --output text)
read -r AK SK ST < <(aws_sb sts assume-role --role-arn "$ROLE_ARN" --role-session-name lookup-bulk-load \
  --duration-seconds 900 --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)
[ -n "${ST:-}" ] || die "assume-role failed"
export M8_ANALYTICS_AWS_ACCESS_KEY_ID="$AK" M8_ANALYTICS_AWS_SECRET_ACCESS_KEY="$SK" M8_ANALYTICS_AWS_SESSION_TOKEN="$ST"
export M8_AWS_REGION="$AWS_SANDBOX_REGION" M8_DOCS_BUCKET="$DOCS_BUCKET" M8_LOOKUP_TABLE="$LOOKUP_TABLE"
ok "credentials ready"

log "Bulk load PostgreSQL -> $LOOKUP_TABLE"
summary=$(docker compose -f docker-compose.yml -f docker-compose.aws.yml run --rm --no-deps -T \
  -e ANALYTICS_CONSUMER_ENABLED=false analytics-service python -m src.services.lookup_load)
printf '  %s\n' "$summary"
pg_rows=$(printf '%s' "$summary" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read().strip().splitlines()[-1])["postgresRows"])')

log "Check (developer session)"
count=$(aws_sb dynamodb scan --table-name "$LOOKUP_TABLE" --select COUNT --query Count --output text)
if [ "$count" -ge "$pg_rows" ]; then ok "table holds $count items (PostgreSQL rows: $pg_rows)"; else die "table holds $count items, expected $pg_rows"; fi
aws_sb dynamodb get-item --table-name "$LOOKUP_TABLE" --key '{"mortgageExternalId":{"S":"MTG-1001"}}' --output text \
  --query 'Item.[mortgageExternalId.S, status.S, outstandingBalance.N, borrowerExternalId.S, source.S]' \
  | awk '{printf "  MTG-1001 -> status %s  balance %s  borrower %s  source %s\n", $2, $3, $4, $5}'

printf '\n\033[1;32mLookup table loaded.\033[0m Read path: GET :8000/api/v1/lookup/mortgages/MTG-1001 (after compose-aws-up.sh)\n'
