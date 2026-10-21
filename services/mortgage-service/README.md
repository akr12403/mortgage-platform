# mortgage-service (port 8080)

Origination and payments bounded context: borrowers, mortgages, loans (approval workflow stub), payments, and the canonical 30-day delinquency rule. **Sole publisher** of mortgage lifecycle events to SNS `capstone-mortgage-lifecycle-dev`.

- Contract: [`docs/api/mortgage-service-openapi.yaml`](../../docs/api/mortgage-service-openapi.yaml)
- Events: `MortgageCreated`, `LoanApproved`, `PaymentReceived`, `PaymentMissed`, `LoanDelinquent` ([catalog](../../docs/architecture/event-catalog.md)). Published **after commit** by `EventPublisherService`.
- Owns tables: `borrower`, `mortgage`, `loan`, `payment`, `idempotency_record`.
- Health: `GET /actuator/health` (container `HEALTHCHECK`).

## Configuration

| Env var | Default | Notes |
| --- | --- | --- |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `localhost` / `5432` / `mortgage_intel` / `mortgage_app` / `postgres` | |
| `SNS_TOPIC_MORTGAGE_EVENTS` | LocalStack ARN for `capstone-mortgage-lifecycle-dev` | |
| `AWS_ENDPOINT_URL` | empty (`http://localhost:4566` in the `dev` profile) | LocalStack only |
| `AWS_REGION` | `us-east-1` | credentials come from the default AWS provider chain |
| `DELINQUENCY_SCAN_CRON` | `0 0 2 * * *` (UTC) | daily batch; trigger on demand with `POST /api/v1/delinquency-evaluations` |

## Notes

- `GET /api/v1/mortgages?borrowerId=` uses an `@EntityGraph` (borrower + loan) to avoid N+1 queries, and responses are DTOs (`MortgageResponse`, `BorrowerResponse`) rather than JPA entities.
- `POST …/payments` accepts an optional `Idempotency-Key` header (same key + same body → original payment, `Idempotent-Replayed: true`; same key + different body → 409).

## Tests

```bash
# from the repo root (the schema contract test reads docs/architecture/events)
docker run --rm -v "$PWD":/workspace -v "$HOME/.m2":/root/.m2 -w /workspace/services/mortgage-service \
  maven:3.9-eclipse-temurin-17 mvn -B test
```
