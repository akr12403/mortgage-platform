# servicing-service (port 8081)

Servicing bounded context. It consumes lifecycle events from SQS `capstone-mortgage-servicing-dev`, maintains `servicing_history` and the `delinquency` snapshot (from `LoanDelinquent`), and serves them over REST.

- Contract: [`docs/api/servicing-service-openapi.yaml`](../../docs/api/servicing-service-openapi.yaml)
- Consumer: `EventConsumerService`. It validates the envelope (schema major 1), dedupes on `eventId` via `event_inbox`, writes history + inbox in one transaction, and acknowledges only after commit. Failures are logged at ERROR with `correlationId`/`eventId`; after 3 receives SQS moves the message to `capstone-mortgage-servicing-dlq-dev`. Unknown event types are skipped (WARN).
- Event → history type: `MortgageCreated→MORTGAGE_CREATED`, `LoanApproved→LOAN_APPROVED`, `PaymentReceived→PAYMENT_POSTED`, `PaymentMissed→PAYMENT_MISSED`, `LoanDelinquent→DELINQUENCY_ASSIGNED`.
- Owns tables: `servicing_history`, `delinquency`, `event_inbox`. Reads `mortgage` only to resolve `MTG-*` IDs.
- Health: `GET /actuator/health` (container `HEALTHCHECK`).

| Env var | Default |
| --- | --- |
| `SQS_QUEUE_SERVICING_EVENTS` | `http://localhost:4566/000000000000/capstone-mortgage-servicing-dev` |
| `SQS_MAX_RECEIVE_COUNT` | `3` (must match the queue RedrivePolicy) |
| `SERVICING_CONSUMER_ENABLED` | `true` |
| `AWS_ENDPOINT_URL`, `AWS_REGION`, `POSTGRES_*` | as for mortgage-service |

Runbook: [`docs/operations/messaging-runbook.md`](../../docs/operations/messaging-runbook.md).

```bash
docker run --rm -v "$PWD":/workspace -v "$HOME/.m2":/root/.m2 -w /workspace/services/servicing-service \
  maven:3.9-eclipse-temurin-17 mvn -B test
```
