# ADR-002: Microservice Decomposition

| Field | Value |
| --- | --- |
| **Status** | Accepted |
| **Milestone** | M5 — Microservices, Events & Containers |
| **Deciders** | Engineering team |
| **Date** | 2026-10-13 (revised 2026-10-20) |
| **Related** | ADR-001 (service data ownership), `docs/architecture/service-ownership-matrix.md`, `docs/architecture/event-catalog.md` |

---

## Context

After M4 the platform had two Spring Boot services and a Python analytics service in one repository, all reading and writing one PostgreSQL schema. Lifecycle side effects (servicing history, delinquency snapshots) were written synchronously by whichever service happened to handle the request, so ownership was unclear, a servicing outage could fail a payment, and there was no audit-friendly record of state changes. M5 asks for documented bounded contexts, contract-first APIs, lifecycle events over SNS → SQS with retries and DLQs, and containerized services.

## Decision

### 1. Three bounded contexts, three deployables

| Service | Bounded context | Owns |
| --- | --- | --- |
| `mortgage-service` (8080, Java) | Origination & payments: borrowers, mortgages, loans/underwriting, payments, mortgage status (incl. the 30-day delinquency rule) | `borrower`, `mortgage`, `loan`, `payment`, `idempotency_record`; **sole publisher** of lifecycle events |
| `servicing-service` (8081, Java) | Servicing record: chronological history and the delinquency snapshot | `servicing_history`, `delinquency`, `event_inbox` |
| `mortgage-analytics-service` (8000, Python) | Portfolio reporting and documents | `document`; read-only on reporting tables |

### 2. Shared database, single writer per table

We keep one PostgreSQL instance for the capstone (cost, local simplicity, M2 seed reuse), but **each table has exactly one writing service** (see the ownership matrix). Cross-context reads are allowed only where listed (servicing reads `mortgage` to resolve `MTG-*` IDs; analytics reads reporting tables). This removes the M4 cross-boundary writes: mortgage-service no longer writes `servicing_history` or `delinquency`; it publishes events and servicing-service projects them.

### 3. Communication

- **Synchronous REST** for client commands and queries, versioned under `/api/v1/`. **No service calls another service's API** at runtime.
- **Asynchronous events** for state changes: `MortgageCreated`, `LoanApproved`, `PaymentReceived`, `PaymentMissed`, `LoanDelinquent`. One SNS topic (`capstone-mortgage-lifecycle-dev`) fans out to one SQS queue per consumer, each with a DLQ (`maxReceiveCount=3`, visibility timeout 30 s). Events are published **after** the producing transaction commits.
- Consumers are **idempotent** on `eventId` and acknowledge only after their own transaction commits.

### 4. Dependency graph is acyclic

`mortgage-service → (events) → servicing-service, analytics-service`. Consumers never call mortgage-service and never publish to the lifecycle topic. The M4 cycle risk — mortgage-service writing servicing tables while servicing-service read mortgage tables — is removed by decision 2.

## API versioning and breaking-change policy

All HTTP contracts are published per service in `docs/api/{service}-openapi.yaml` as version `v1` and served under `/api/v1/`. **Non-breaking** changes (new optional request fields, new response fields, new endpoints, new error codes) ship in place. **Breaking** changes (removing or renaming fields, changing types, formats or semantics, tightening validation, changing status codes or the error envelope, changing paths) require a new `/api/v2/` path, served alongside `v1` for at least one milestone, with the deprecation announced in the OpenAPI `description` and the PR. Event payloads follow the same rule through `schemaVersion` (see the event catalog's schema evolution policy).

## Consumer-driven expectations (servicing-service on mortgage IDs)

servicing-service relies on these producer guarantees; changing any of them is a breaking change:

1. Every event payload carries `mortgageExternalId` matching `^MTG-[0-9]{4}$` (enforced by the JSON Schemas and by `@Pattern` on `POST /api/v1/mortgages`).
2. The ID is the business ID, never the internal UUID, and is immutable once created (unique `mortgage.mortgage_external_id`).
3. `MortgageCreated` for a mortgage is committed before any other event for that mortgage is published (publish-after-commit + creation order). If a consumer still cannot resolve the ID, it does not acknowledge, so SQS retries and finally dead-letters the message.
4. `correlationId` is always present; for API-triggered events it equals the request's `X-Correlation-Id`.

These expectations are checked by `EventSchemaContractTest` (producer output vs schema) and `EventConsumerServiceTest` (consumer behavior on unknown or invalid IDs).

## Consequences

**Positive**
- Clear ownership; servicing or analytics outages no longer fail payments (events wait in SQS).
- An auditable, replayable history of lifecycle changes; DLQs isolate poison messages.
- Each service builds, tests and ships as its own container.

**Negative / trade-offs**
- **Eventual consistency**: servicing history and the delinquency snapshot lag the write by roughly one poll interval (~2–5 s locally).
- **Shared-database coupling remains for reads**. Path to remove it: per-service schemas or databases with read models built from events (candidate for M8/M9).
- **Publish-after-commit is not an outbox**: if SNS is unavailable right after commit, the event is lost (logged at ERROR with its `eventId`). A transactional outbox table plus relay is the follow-up for production readiness (M10).
- More moving parts (LocalStack, init container, DLQs) — covered by `docs/operations/messaging-runbook.md`.
