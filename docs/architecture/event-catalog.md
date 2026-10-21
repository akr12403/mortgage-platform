# Event Catalog

Mortgage lifecycle events are published by `mortgage-service` to the SNS topic `capstone-mortgage-lifecycle-dev` and fanned out to one SQS queue per consumer (raw message delivery). Every event is validated by a JSON Schema (draft 2020-12) in [`events/`](./events/); example instances live in [`events/examples/`](./events/examples/).

| Event | Schema version | Producer (trigger) | Consumers | Schema |
| --- | --- | --- | --- | --- |
| `MortgageCreated` | `1.0` | `mortgage-service` — `POST /api/v1/mortgages` persists a mortgage in `PENDING` | `servicing-service` (history `MORTGAGE_CREATED`), `analytics-service` (snapshot refresh) | [`mortgage-created.schema.json`](./events/mortgage-created.schema.json) |
| `LoanApproved` | `1.0` | `mortgage-service` — approval workflow stub: `POST /api/v1/mortgages/{id}/underwriting-decision` with `APPROVED`, or a create request whose nested loan is `APPROVED`. Mortgage moves `PENDING → ACTIVE` | `servicing-service` (`LOAN_APPROVED`), `analytics-service` | [`loan-approved.schema.json`](./events/loan-approved.schema.json) |
| `PaymentReceived` | `1.0` | `mortgage-service` — `POST /api/v1/mortgages/{id}/payments` with status `POSTED`; balance reduced | `servicing-service` (`PAYMENT_POSTED`), `analytics-service` | [`payment-received.schema.json`](./events/payment-received.schema.json) |
| `PaymentMissed` | `1.0` | `mortgage-service` — a `FAILED`/`REVERSED` payment attempt for a due date on or before today with no `POSTED` payment for that date, **or** the delinquency batch (`POST /api/v1/delinquency-evaluations`, daily 02:00 UTC) finding an unpaid installment 30+ days past due | `servicing-service` (`PAYMENT_MISSED`), `analytics-service` | [`payment-missed.schema.json`](./events/payment-missed.schema.json) |
| `LoanDelinquent` | `1.0` | `mortgage-service` — same paths as `PaymentMissed` when the installment is **30+ days** past due and the mortgage is `ACTIVE`; mortgage moves `ACTIVE → DELINQUENT` | `servicing-service` (`DELINQUENCY_ASSIGNED` + upserts the `delinquency` snapshot), `analytics-service` | [`loan-delinquent.schema.json`](./events/loan-delinquent.schema.json) |

Payload fields match the capstone handbook's `reference/payload-examples.json` exactly. Delinquency semantics follow `guides/standards.md`: `delinquentSince = dueDate + 30 days`; severity `MODERATE` (30–59 days), `SEVERE` (60–89), `CRITICAL` (90+).

## Envelope

```json
{
  "eventId": "550e8400-e29b-41d4-a716-446655440001",
  "eventType": "PaymentReceived",
  "schemaVersion": "1.0",
  "occurredAt": "2026-03-15T14:30:00Z",
  "correlationId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "payload": { "mortgageExternalId": "MTG-1001", "paymentAmount": 1850.00, "paidDate": "2026-03-02", "outstandingBalanceAfter": 317650.00 }
}
```

| Field | Rule |
| --- | --- |
| `eventId` | UUID v4, unique per event. Consumers dedupe on it (`event_inbox` in servicing, bounded cache in analytics). |
| `eventType` | One of the names above. Also sent as SNS message attribute `eventType`. |
| `schemaVersion` | `MAJOR.MINOR`. Also sent as message attribute. |
| `occurredAt` | ISO-8601 UTC. |
| `correlationId` | The `X-Correlation-Id` of the HTTP request that caused the event (generated UUID for the scheduled batch). Also sent as message attribute and put in consumer log MDC. |
| `payload` | Business identifiers only (`MTG-*`, `BOR-*`, `LOAN-*`) — never internal UUIDs. |

## Delivery guarantees

- **Publish after commit**: events are built inside the business transaction but sent to SNS only after it commits, so rolled-back writes never produce events. A publish failure after commit is logged at ERROR with the `eventId` (a transactional outbox is the M9/M10 hardening step).
- **At-least-once** delivery to consumers; consumers are idempotent on `eventId`.
- **Retries / DLQ**: consumers acknowledge only after success. Visibility timeout 30 s; after 3 receives SQS moves the message to the consumer's DLQ (`…-dlq-dev`). The final failed attempt is logged at ERROR as "SQS will move … to the DLQ". See [`docs/operations/messaging-runbook.md`](../operations/messaging-runbook.md).

## Schema evolution policy

- **Minor (`1.0 → 1.1`)**: additive and optional fields only. Payload schemas allow additional properties, so 1.x consumers keep working.
- **Major (`2.0`)**: renamed/removed/retyped fields or changed meaning. Publish the new major alongside the old one (or on a new topic) until every consumer is migrated. Consumers **reject** unsupported majors (the message is not acknowledged and ends in the DLQ), so a breaking change can never be silently misread.
- Unknown `eventType`s are acknowledged and skipped by consumers (logged at WARN), so new event types can be added without coordinated deploys.
- Every schema change is recorded in an ADR and in this catalog; `EventSchemaContractTest` (mortgage-service) and `tests/contract/test_event_contracts.py` fail if producer output or examples drift from the schemas.
