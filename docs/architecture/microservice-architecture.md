# Microservice Architecture

## Objective
This project implements the Milestone 5 architecture as a containerized, event-driven mortgage platform centered on three runnable services: `mortgage-service`, `servicing-service`, and `mortgage-analytics-service`.

The architecture is designed to separate responsibilities while preserving a local-development baseline that is simple to run and demonstrate in Docker Compose.

## Service Map

| Service | Port | Responsibility | Writes | Reads | Produces | Consumes |
| --- | --- | --- | --- | --- | --- | --- |
| `mortgage-service` | `8080` | origination, borrower onboarding, payment posting, lifecycle state changes | borrower, mortgage, loan, payment, payment history | canonical DB | `MortgageCreated`, `LoanApproved`, `PaymentReceived`, `PaymentMissed` | none |
| `servicing-service` | `8081` | servicing history, delinquency evaluation, event projection | `servicing_history`, `event_inbox` | canonical DB + SQS | none | `MortgageCreated`, `LoanApproved`, `PaymentReceived`, `PaymentMissed`, `LoanDelinquent` |
| `mortgage-analytics-service` | `8000` | portfolio metrics, borrower risk, payment trends | no mortgage-domain writes | canonical DB | none | none |

## Runtime Topology
- PostgreSQL 17 runs the canonical schema and synthetic seed data.
- LocalStack provides SNS and SQS for asynchronous event delivery.
- The `messaging-init` container creates the mortgage lifecycle topic and servicing queue with redrive policy.
- Compose wires each service with environment variables for Postgres, LocalStack, and queue/topic endpoints.

## Message Flow
1. `mortgage-service` creates or updates a mortgage, payment, or loan state.
2. It serializes a domain event into an AWS SNS event envelope:
   - `eventId`
   - `eventType`
   - `schemaVersion`
   - `occurredAt`
   - `correlationId`
   - `payload`
3. SNS fans out to the servicing SQS queue.
4. `servicing-service` polls the queue and validates the envelope.
5. It resolves `mortgageExternalId` to the internal UUID in Postgres.
6. It writes a `servicing_history` row and inserts a dedupe record into `event_inbox`.
7. The message is acknowledged only after the transaction commits.

## DLQ and Retry Policy
- Queue: `capstone-mortgage-servicing-dev`
- DLQ: `capstone-mortgage-servicing-dlq-dev`
- Trigger: `maxReceiveCount=3`
- Visibility timeout: `30` seconds

This means a bad or malformed event will be retried up to three times before being moved to the DLQ.

## Contract-first Standards
All service APIs are documented as runnable HTTP contracts and must be validated before milestone signoff.

### HTTP contract rules
- Business IDs are exposed externally: `BOR-*`, `MTG-*`, `LOAN-*`
- Internal DB identifiers remain UUIDs and are not exposed in public APIs
- Error envelopes include `code`, `message`, `correlationId`, and `timestamp`
- API responses must be camelCase for JS/JSON consumers

### Event contract rules
- Event payloads use external business IDs in the `payload`
- Event payloads must never include internal UUIDs in the public contract
- Event type names match the project catalog
- Consumer validation should reject malformed envelope data and missing mortgage IDs

## Definition of Done for M5
A Milestone 5 review is complete when all of the following are demonstrated in a local environment:
- Compose starts all services with health checks
- Both Java services pass their test suites
- Analytics passes its Python tests
- A new mortgage and loan can be created and retrieved
- A payment can be posted and reflected in balance updates
- A delinquency transition can be triggered and persisted
- Mortgage lifecycle events are published to SNS and consumed by SQS
- The dedupe model (`event_inbox`) prevents duplicate side effects
- A poisoned event reaches the DLQ after retry thresholds are exhausted
- Architecture docs, event catalog, and API contract files match the implementation

## Known implementation limits
This project is intentionally explicit about the current limits of M5:
- `mortgage-analytics-service` reads the canonical PostgreSQL schema for reporting, and is not currently an SQS consumer.
- The event catalog files are examples and not formal JSON-Schema validators.
- The local stack is enterprise-style education architecture, not a production AWS deployment with IAM hardening, KMS, and multi-region topology.

## Runtime validation commands
```bash
docker compose ps
docker compose exec -T localstack awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/capstone-mortgage-servicing-dev \
  --attribute-names RedrivePolicy VisibilityTimeout
curl -sS http://localhost:8080/actuator/health
curl -sS http://localhost:8081/actuator/health
curl -sS http://localhost:8000/health
```
