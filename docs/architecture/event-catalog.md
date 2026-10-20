# Event Catalog

This document catalogs all asynchronous event types published across the Enterprise Mortgage Platform's event-driven architecture. All events conform to standard envelope attributes (`eventId`, `eventType`, `schemaVersion`, `occurredAt`, `correlationId`) and are routed via AWS SNS/SQS.

| Event Name | Schema Version | Producer Service | Consumer Service(s) | Description / Trigger Condition | Schema File Reference |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`MortgageCreated`** | `1.0` | `mortgage-service` | `servicing-service` | Mortgage persisted in `PENDING` state. | [`mortgage-created.json`](./events/mortgage-created.json) |
| **`LoanApproved`** | `1.0` | `mortgage-service` | `servicing-service` | Nested loan persisted with decision `APPROVED`. | [`loan-approved.json`](./events/loan-approved.json) |
| **`PaymentReceived`** | `1.0` | `mortgage-service` | `servicing-service` | Payment with `POSTED` status is persisted and balance updated. | [`payment-received.json`](./events/payment-received.json) |
| **`PaymentMissed`** | `1.0` | `mortgage-service` | `servicing-service` | Failed/reversed payment attempt occurs on or after its due date. | [`payment-missed.json`](./events/payment-missed.json) |
| **`LoanDelinquent`** | `1.0` | Planned; producer not wired | `servicing-service` when produced | Canonical 30-day delinquency transition. | [`loan-delinquent.json`](./events/loan-delinquent.json) |

---

## Event Envelope Structure
Every event payload is wrapped in a standard JSON envelope:
- **`eventId`**: Unique UUID v4 identifying the event instance.
- **`eventType`**: String matching the catalog event name.
- **`schemaVersion`**: Version string (`1.0`) for consumer compatibility.
- **`occurredAt`**: ISO-8601 UTC event timestamp.
- **`correlationId`**: Propagated request correlation ID.
- **`payload`**: Domain data; use external business IDs such as `MTG-1001`, not internal database UUIDs.

## Consumer Scope

`servicing-service` consumes the events listed above. `mortgage-analytics-service` currently reads PostgreSQL and is not an event consumer in the implementation.