# Service Ownership Matrix

The capstone runs one PostgreSQL database (`mortgage_intel`, schema in `database/migrations/`). Isolation is enforced at the **table-write** level: each table has exactly one writing service. Other services may only **read** a table when listed below (see ADR-002). UUIDs are internal keys; `BOR-*`, `MTG-*`, `LOAN-*` are the only identifiers exposed in APIs and events.

## Ownership by service

| Service | Port | Writes (owns) | Reads (not owned) | APIs owned | Events produced | Events consumed |
| --- | --- | --- | --- | --- | --- | --- |
| **`mortgage-service`** | 8080 | `borrower`, `mortgage` (incl. `status`), `loan`, `payment`, `idempotency_record` | — | `POST /api/v1/borrowers`, `GET /api/v1/borrowers/{id}`<br>`POST /api/v1/mortgages`, `GET /api/v1/mortgages/{id}`, `GET /api/v1/mortgages?borrowerId=`<br>`POST /api/v1/mortgages/{id}/underwriting-decision`<br>`POST`/`GET /api/v1/mortgages/{id}/payments`<br>`POST /api/v1/delinquency-evaluations` | `MortgageCreated`, `LoanApproved`, `PaymentReceived`, `PaymentMissed`, `LoanDelinquent` | — |
| **`servicing-service`** | 8081 | `servicing_history`, `delinquency` (snapshot projected from `LoanDelinquent`), `event_inbox` | `mortgage` (resolve `MTG-*` → UUID, current status) | `GET /api/v1/mortgages/{id}/servicing-history`<br>`GET /api/v1/mortgages/{id}/delinquency`<br>`POST /api/v1/mortgages/{id}/servicing-events` | — | all five, via `capstone-mortgage-servicing-dev` |
| **`mortgage-analytics-service`** | 8000 | `document` (M3 upload metadata) | `borrower`, `mortgage`, `payment`, `delinquency` (reporting) | `GET /health`, `/api/v1/analytics/portfolio-summary`, `/delinquency`, `/borrowers/{id}/risk-summary`, `/payment-trends`, `/event-stats`, `POST /api/v1/documents/upload` | — | all five, via `capstone-mortgage-analytics-dev` (snapshot refresh) |
| `mortgage-knowledge-assistant` | 8001 | (M7) | — | (M7) | — | — |

## Ownership by table

| Table | Writer | Readers |
| --- | --- | --- |
| `borrower` | mortgage-service | analytics |
| `mortgage` | mortgage-service | servicing (ID lookup/status), analytics |
| `loan` | mortgage-service | — |
| `payment` | mortgage-service | analytics |
| `idempotency_record` | mortgage-service | — |
| `servicing_history` | servicing-service | — |
| `delinquency` | servicing-service (from `LoanDelinquent`) | analytics |
| `event_inbox` | servicing-service | — |
| `document` | analytics-service | — |

## Messaging resources

| Resource | Owner | Notes |
| --- | --- | --- |
| SNS `capstone-mortgage-lifecycle-dev` | mortgage-service (publisher) | only publisher |
| SQS `capstone-mortgage-servicing-dev` + DLQ `capstone-mortgage-servicing-dlq-dev` | servicing-service | maxReceiveCount 3, visibility 30 s |
| SQS `capstone-mortgage-analytics-dev` + DLQ `capstone-mortgage-analytics-dlq-dev` | analytics-service | maxReceiveCount 3, visibility 30 s |

## Dependency direction (no cycles)

```text
mortgage-service ──(SNS events)──> servicing-service
        │                     └──> analytics-service
        └── no runtime calls to either consumer
```

- No service calls another service's HTTP API at runtime; the only cross-service runtime coupling is the one-way event flow above.
- Consumers never publish back to the lifecycle topic, so there is no event loop.
- The remaining coupling is **shared-database reads** (servicing → `mortgage`, analytics → reporting tables). It is acyclic and recorded in ADR-002 together with the path to remove it (per-service schemas + read models built from events).

## Rules

1. A service writes only the tables it owns. Changes to another service's data go through its API or an event.
2. Never derive a database ID from a business ID; resolve `MTG-*` via the `mortgage_external_id` unique column.
3. Adding a reader to a table requires updating this matrix in the same PR.
