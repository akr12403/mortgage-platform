# Event Catalog

This document catalogs all asynchronous event types published across the Enterprise Mortgage Platform's event-driven architecture. All events conform to standard envelope attributes (`eventId`, `eventType`, `schemaVersion`, `occurredAt`, `correlationId`) and are routed via AWS SNS/SQS.

| Event Name | Schema Version | Producer Service | Consumer Service(s) | Description / Trigger Condition | Schema File Reference |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`MortgageCreated`** | `1.0`[cite: 2] | `mortgage-service`[cite: 3] | `servicing-service`, `analytics-service`[cite: 3] | Fired immediately when a new mortgage application is successfully registered in `PENDING` state[cite: 2, 3]. | [`mortgage-created.json`](./events/mortgage-created.json) |
| **`LoanApproved`** | `1.0`[cite: 2] | `mortgage-service`[cite: 3] | `servicing-service`[cite: 3] | Fired when underwriter approval is recorded for an existing mortgage application[cite: 2, 3]. | [`loan-approved.json`](./events/loan-approved.json) |
| **`PaymentReceived`** | `1.0`[cite: 2] | `mortgage-service`[cite: 3] | `servicing-service`[cite: 3] | Fired when a payment is successfully posted against an active mortgage[cite: 2, 3]. | [`payment-received.json`](./events/payment-received.json) |
| **`PaymentMissed`** | `1.0`[cite: 2] | `mortgage-service`[cite: 3] | `servicing-service`[cite: 3] | Fired when a scheduled payment billing date passes without a matching payment[cite: 2, 3]. | [`payment-missed.json`](./events/payment-missed.json) |
| **`LoanDelinquent`** | `1.0`[cite: 2] | `mortgage-service`[cite: 3] | `servicing-service`[cite: 3] | Fired when a mortgage breaches the canonical 30-day delinquency window[cite: 2, 3]. | [`loan-delinquent.json`](./events/loan-delinquent.json) |

---

## Event Envelope Structure
Every event payload is wrapped in a standard JSON envelope:
- **`eventId`**: Unique UUID v4 identifying the specific event instance[cite: 2].
- **`eventType`**: String name matching the catalog definition[cite: 2].
- **`schemaVersion`**: Version string (default `1.0`) for consumer compatibility checks[cite: 2].
- **`occurredAt`**: ISO-8601 UTC timestamp of when the event was generated[cite: 1, 2].
- **`correlationId`**: Propagated transaction ID (`X-Correlation-Id`) linking HTTP requests to downstream asynchronous logs[cite: 1, 2].
- **`payload`**: Domain-specific object containing event properties[cite: 2].