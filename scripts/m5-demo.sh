#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== M5 demonstration =="

docker compose ps

curl -sS -i http://localhost:8080/actuator/health | head
curl -sS -i http://localhost:8081/actuator/health | head
curl -sS -i http://localhost:8000/health | head

echo "== portfolio summary =="
curl -sS http://localhost:8000/api/v1/analytics/portfolio-summary

echo "\n== create mortgage =="
curl -sS -i -X POST http://localhost:8080/api/v1/mortgages \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: m5-demo-001' \
  -d '{
    "mortgageExternalId":"MTG-9016",
    "borrowerExternalId":"BOR-001",
    "originalAmount":320000.00,
    "outstandingBalance":318500.00,
    "originationDate":"2025-06-01",
    "loan":{
      "loanExternalId":"LOAN-9016",
      "interestRate":0.0650,
      "termMonths":360,
      "underwritingDecision":"APPROVED"
    }
  }'

echo "\n== servicing history =="
curl -sS http://localhost:8081/api/v1/mortgages/MTG-9016/servicing-history

echo "\n== payment posted =="
curl -sS -i -X POST http://localhost:8080/api/v1/mortgages/MTG-9016/payments \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: m5-demo-002' \
  -d '{
    "dueDate":"2026-10-01",
    "paidDate":"2026-10-02",
    "amount":1500.00,
    "status":"POSTED"
  }'

echo "\n== delinquency demo =="
curl -sS -i -X POST http://localhost:8080/api/v1/mortgages/MTG-9016/payments \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: m5-demo-003' \
  -d '{
    "dueDate":"2026-08-01",
    "paidDate":null,
    "amount":1250.00,
    "status":"FAILED"
  }'

curl -sS http://localhost:8081/api/v1/mortgages/MTG-9016/delinquency

echo "\n== poison message to DLQ =="
docker compose exec -T localstack awslocal sqs send-message \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/capstone-mortgage-servicing-dev \
  --message-body '{
    "eventId":"80b4c87c-77d1-4384-a737-3c595b311402",
    "eventType":"MortgageCreated",
    "schemaVersion":"1.0",
    "occurredAt":"2026-10-20T12:00:00Z",
    "correlationId":"80b4c87c-77d1-4384-a737-3c595b311403",
    "payload":{"mortgageExternalId":"MTG-NOT-FOUND","borrowerExternalId":"BOR-001","originalAmount":100000.00,"status":"PENDING"}
  }'

echo "\n== DLQ count =="
docker compose exec -T localstack awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/capstone-mortgage-servicing-dlq-dev \
  --attribute-names ApproximateNumberOfMessages

echo "\n== M5 demo complete =="
