#!/usr/bin/env bash
# M5 demo — follows the milestone demo scenario end to end against the running compose stack.
#   bash scripts/m5-demo.sh            # full run (~3 minutes, mostly waiting for the DLQ redrive)
#   SKIP_DLQ=1 bash scripts/m5-demo.sh # skip the poison-message step
# Prereq: docker compose up --build -d   (all containers healthy)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MS=http://localhost:8080
SS=http://localhost:8081
AS=http://localhost:8000
Q=http://localhost:4566/000000000000

N=$(( (RANDOM % 4000) + 5000 ))          # 5000-8999: never collides with seed IDs
MTG="MTG-$N"
LOAN="LOAN-$N"
CID="$(python3 -c 'import uuid; print(uuid.uuid4())')"

days_ago() {  # portable (macOS BSD date / GNU date)
  date -u -v-"$1"d +%F 2>/dev/null || date -u -d "$1 days ago" +%F
}

step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
json() { python3 -m json.tool; }
call() {  # call METHOD URL [BODY] [extra curl args...]
  local method=$1 url=$2 body=${3:-}
  shift 3 || shift $#
  if [[ -n "$body" ]]; then
    curl -sS -X "$method" "$url" -H 'Content-Type: application/json' -H "X-Correlation-Id: $CID" "$@" -d "$body"
  else
    curl -sS -X "$method" "$url" -H "X-Correlation-Id: $CID" "$@"
  fi
}
awsl() { docker compose exec -T localstack awslocal "$@"; }

step "0. Stack health (all must be healthy)"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
for url in $MS/actuator/health $SS/actuator/health $AS/health; do
  printf '%-40s %s\n' "$url" "$(curl -sS "$url")"
done
echo "Demo mortgage: $MTG   correlationId: $CID"

step "1. Create mortgage -> MortgageCreated (status PENDING)"
call POST $MS/api/v1/mortgages "{
  \"mortgageExternalId\":\"$MTG\",\"borrowerExternalId\":\"BOR-001\",
  \"originalAmount\":320000.00,\"outstandingBalance\":318500.00,\"originationDate\":\"2025-06-01\",
  \"loan\":{\"loanExternalId\":\"$LOAN\",\"interestRate\":0.0650,\"termMonths\":360,\"underwritingDecision\":\"PENDING\"}}" | json

step "2. Approval workflow stub -> LoanApproved (PENDING -> ACTIVE)"
call POST $MS/api/v1/mortgages/$MTG/underwriting-decision '{"decision":"APPROVED","decidedByRole":"UNDERWRITER"}' | json

step "3. Post payment with Idempotency-Key -> PaymentReceived"
PAY="{\"dueDate\":\"$(days_ago 5)\",\"paidDate\":\"$(days_ago 3)\",\"amount\":1850.00,\"status\":\"POSTED\"}"
call POST $MS/api/v1/mortgages/$MTG/payments "$PAY" -H "Idempotency-Key: pay-$MTG-1" -i | sed -n '1p;/Idempotent-Replayed/p'
echo "Replaying the same request (expect Idempotent-Replayed: true and NO second event):"
call POST $MS/api/v1/mortgages/$MTG/payments "$PAY" -H "Idempotency-Key: pay-$MTG-1" -i | sed -n '1p;/Idempotent-Replayed/p'

step "4. Consumer processed events -> servicing history (MORTGAGE_CREATED, LOAN_APPROVED, PAYMENT_POSTED)"
sleep 6
call GET $SS/api/v1/mortgages/$MTG/servicing-history | json

step "5. Failed payment 45 days past due -> PaymentMissed + LoanDelinquent"
call POST $MS/api/v1/mortgages/$MTG/payments \
  "{\"dueDate\":\"$(days_ago 45)\",\"paidDate\":null,\"amount\":1850.00,\"status\":\"FAILED\"}" | json
sleep 6
echo "mortgage status:"; call GET $MS/api/v1/mortgages/$MTG | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["outstandingBalance"])'
echo "delinquency snapshot (servicing-service):"; call GET $SS/api/v1/mortgages/$MTG/delinquency | json
echo "latest history:"; call GET $SS/api/v1/mortgages/$MTG/servicing-history | python3 -c 'import json,sys; [print(" ", e["eventType"], "-", e["description"]) for e in json.load(sys.stdin)["events"]]'
echo "analytics (delinquency rate = DELINQUENT/(ACTIVE+DELINQUENT)):"; call GET $AS/api/v1/analytics/portfolio-summary | json
echo "analytics consumer:"; call GET $AS/api/v1/analytics/event-stats | python3 -c 'import json,sys; d=json.load(sys.stdin); print(" ", d.get("eventsProcessed"), "last:", (d.get("lastEvent") or {}).get("eventType"))'

step "6. Correlation ID propagated HTTP -> logs -> events -> consumer logs"
docker compose logs --no-color mortgage-service servicing-service 2>/dev/null | grep "$CID" | tail -8 || true

if [[ "${SKIP_DLQ:-0}" != "1" ]]; then
  step "7. Break the consumer: poison event for unknown MTG-0000 -> retries -> DLQ"
  BEFORE=$(awsl sqs get-queue-attributes --queue-url $Q/capstone-mortgage-servicing-dlq-dev \
    --attribute-names ApproximateNumberOfMessages --query 'Attributes.ApproximateNumberOfMessages' --output text)
  POISON_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  awsl sqs send-message --queue-url $Q/capstone-mortgage-servicing-dev --message-body "{
    \"eventId\":\"$POISON_ID\",\"eventType\":\"MortgageCreated\",\"schemaVersion\":\"1.0\",
    \"occurredAt\":\"$(date -u +%FT%TZ)\",\"correlationId\":\"$CID\",
    \"payload\":{\"mortgageExternalId\":\"MTG-0000\",\"borrowerExternalId\":\"BOR-001\",\"originalAmount\":100000.00,\"status\":\"PENDING\"}}" >/dev/null
  echo "Sent poison eventId=$POISON_ID. DLQ depth before: $BEFORE. Waiting for 3 receives (visibility 30 s each)..."
  for i in $(seq 1 30); do
    sleep 6
    NOW=$(awsl sqs get-queue-attributes --queue-url $Q/capstone-mortgage-servicing-dlq-dev \
      --attribute-names ApproximateNumberOfMessages --query 'Attributes.ApproximateNumberOfMessages' --output text)
    printf '  t=%3ss DLQ depth=%s\n' $((i * 6)) "$NOW"
    if (( NOW > BEFORE )); then break; fi
  done
  docker compose logs --no-color servicing-service 2>/dev/null | grep "$POISON_ID" | grep ERROR | cut -c1-220 || true
fi

step "8. docker compose ps (all healthy)"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'

echo -e "\nDone. Mortgage $MTG, correlationId $CID."
