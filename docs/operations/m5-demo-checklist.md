# M5 Demo Checklist

## Goal
Demonstrate the mortgage intelligence platform as a containerized, contract-first microservice architecture with event-driven servicing and analytics.

## Required runtime state
Before starting:
- Docker Compose is running
- PostgreSQL is healthy
- LocalStack is healthy
- `mortgage-service` is healthy on `:8080`
- `servicing-service` is healthy on `:8081`
- `analytics-service` is healthy on `:8000`

```bash
cd ~/projects/mortgage-platform
docker compose ps
curl -sS http://localhost:8080/actuator/health
curl -sS http://localhost:8081/actuator/health
curl -sS http://localhost:8000/health
```

## 1. Queue and DLQ verification
```bash
docker compose exec -T localstack awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/capstone-mortgage-servicing-dev \
  --attribute-names RedrivePolicy VisibilityTimeout

docker compose exec -T localstack awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/capstone-mortgage-servicing-dlq-dev \
  --attribute-names ApproximateNumberOfMessages
```

Expected result:
- `RedrivePolicy` includes `maxReceiveCount=3`
- `VisibilityTimeout` is `30`
- the DLQ exists and is reachable

## 2. Portfolio analytics baseline
```bash
curl -sS http://localhost:8000/api/v1/analytics/portfolio-summary
curl -sS http://localhost:8000/api/v1/analytics/delinquency
curl -sS http://localhost:8000/api/v1/analytics/borrowers/BOR-001/risk-summary
curl -sS "http://localhost:8000/api/v1/analytics/payment-trends?from=2025-01-01&to=2026-12-31"
```

Expected result:
- portfolio summary returns the overall counts and balances
- delinquency route returns mortgage risk details
- borrower-risk endpoint returns a single borrower summary or a `404` with the shared error envelope
- payment trends returns a `from`, `to`, and `buckets` body

## 3. Mortgage creation
```bash
curl -sS -i -X POST http://localhost:8080/api/v1/mortgages \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: M5-demo-001' \
  -d '{
    "mortgageExternalId":"MTG-9015",
    "borrowerExternalId":"BOR-001",
    "originalAmount":320000.00,
    "outstandingBalance":318500.00,
    "originationDate":"2025-06-01",
    "loan":{
      "loanExternalId":"LOAN-9015",
      "interestRate":0.0650,
      "termMonths":360,
      "underwritingDecision":"APPROVED"
    }
  }'
```

Expected result:
- `201 Created`
- response contains `mortgageExternalId`, `borrowerExternalId`, and nested `loan`

Validate the canonical DB and servicing history:

```bash
curl -sS http://localhost:8080/api/v1/mortgages/MTG-9015
curl -sS http://localhost:8081/api/v1/mortgages/MTG-9015/servicing-history

docker compose exec -T postgres psql -U mortgage_app -d mortgage_intel \
  -c "SELECT mortgage_external_id, status, outstanding_balance FROM mortgage WHERE mortgage_external_id='MTG-9015';" \
  -c "SELECT event_type, description, event_time FROM servicing_history WHERE mortgage_id=(SELECT id FROM mortgage WHERE mortgage_external_id='MTG-9015') ORDER BY event_time;"
```

Expected result:
- service returns the nested loan and approved underwriting decision
- servicing history contains `MortgageCreated` and `LoanApproved`

## 4. Payment posting
```bash
curl -sS -i -X POST http://localhost:8080/api/v1/mortgages/MTG-9015/payments \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: M5-demo-002' \
  -d '{
    "dueDate":"2026-10-01",
    "paidDate":"2026-10-02",
    "amount":1500.00,
    "status":"POSTED"
  }'
```

Expected result:
- `200 OK`
- outstanding balance is reduced by the payment amount
- payment appears in `GET /api/v1/mortgages/{id}/payments`
- servicing history contains `PaymentReceived`

## 5. Delinquency transition
```bash
curl -sS -i -X POST http://localhost:8080/api/v1/mortgages/MTG-9015/payments \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: M5-demo-003' \
  -d '{
    "dueDate":"2026-08-01",
    "paidDate":null,
    "amount":1250.00,
    "status":"FAILED"
  }'

curl -sS http://localhost:8081/api/v1/mortgages/MTG-9015/delinquency
curl -sS http://localhost:8081/api/v1/mortgages/MTG-9015/servicing-history
```

Expected result:
- mortgage becomes `DELINQUENT` when 30+ days past due and no successful payment exists
- delinquency snapshot includes `daysPastDue` and `severity`
- history includes `PaymentMissed` and `LoanDelinquent`

## 6. Poison-event DLQ test
```bash
docker compose exec -T localstack awslocal sqs send-message \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/capstone-mortgage-servicing-dev \
  --message-body '{
    "eventId":"80b4c87c-77d1-4384-a737-3c595b311401",
    "eventType":"MortgageCreated",
    "schemaVersion":"1.0",
    "occurredAt":"2026-10-20T12:00:00Z",
    "correlationId":"80b4c87c-77d1-4384-a737-3c595b311402",
    "payload":{"mortgageExternalId":"MTG-NOT-FOUND","borrowerExternalId":"BOR-001","originalAmount":100000.00,"status":"PENDING"}
  }'
```

Wait ~90 seconds, then check:

```bash
docker compose logs --tail=80 servicing-service
docker compose exec -T localstack awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/capstone-mortgage-servicing-dlq-dev \
  --attribute-names ApproximateNumberOfMessages
```

Expected result:
- consumer logs a failure and leaves the message to retry
- after three receives, the event appears in the DLQ
- no `servicing_history` row is created for `MTG-NOT-FOUND`

## 7. Review checklist
Use this checklist during M5 review:
- [ ] Compose stack is healthy and all services are up
- [ ] Java and Python test suites pass
- [ ] Mortgage create route returns the correct business IDs and nested loan
- [ ] Payment path updates balance correctly and emits `PaymentReceived`
- [ ] Delinquency path triggers `LoanDelinquent` and stores severity
- [ ] SQS + DLQ redrive policy is configured with `maxReceiveCount=3`
- [ ] The consumer deduplicates repeated events via `event_inbox`
- [ ] Error responses contain `code`, `message`, `correlationId`, and `timestamp`
- [ ] Documentation and runtime behavior match the event examples and contracts

## 8. M5 sign-off statement
The milestone is considered complete for local-capstone demonstration only when all of the above pass and any implementation limits are documented as explicit decisions, not hidden assumptions.
