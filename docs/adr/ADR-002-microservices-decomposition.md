# ADR-002: Microservice Decomposition

| Field | Value |
| --- | --- |
| **Status** | Accepted |
| **Milestone** | M5 (Microservices, Events & Containers)[cite: 10] |
| **Deciders** | Engineering Team / Architecture Group |
| **Date** | 2026-10-13 |

---

## Context

As the Enterprise Mortgage Platform evolves past Milestone 4, the system requires clear separation of concerns between core loan origination/management (`mortgage-service`) and post-closing operations/servicing history tracking (`servicing-service`). Managing these distinct business domains within a tightly coupled or monolithic structure limits independent scaling, increases blast radiuses during failures, and muddies data ownership boundaries.

We needed a formal architectural strategy to decouple these services while ensuring reliable cross-domain communication, auditability, and adherence to domain-driven design principles.

---

## Decision

We have formally decided to decompose the platform into **loosely coupled, independently deployable Spring Boot microservices** representing distinct bounded contexts:

1. **Domain-Driven Service Splitting**:
   - **`mortgage-service` (Port 8080)** owns borrower accounts, loan applications, mortgage terms, and financial payment transactions.
   - **`servicing-service` (Port 8081)** owns post-closing audit trails (`servicing_history`) and risk/delinquency evaluation workflows.

2. **Strict Database Isolation**:
   - Each microservice maintains exclusive ownership of its underlying database tables. Cross-domain database joins or direct writes across service boundaries are strictly prohibited.

3. **Hybrid Communication Model**:
   - **Synchronous (REST)**: Used for client-facing transactional queries and direct action triggers (e.g., fetching mortgage details, posting a payment).
   - **Asynchronous (Event-Driven via AWS SNS/SQS)**: Used for state transition notifications (`MortgageCreated`, `PaymentReceived`, `PaymentMissed`, `LoanDelinquent`) to propagate changes without blocking client threads[cite: 10].

---

## Consequences

### Positive (Benefits)
- **Independent Scalability**: High-traffic components (such as payment processing and servicing logs) can be scaled independently of origination pipelines.
- **Fault Isolation**: Failures in the servicing domain do not block core mortgage origination workflows.
- **Clear Ownership**: Teams or individual developers have unambiguous boundaries over code, APIs, and database persistence layers.

### Negative / Trade-offs (Mitigations)
- **Eventual Consistency**: Asynchronous event publishing means downstream consumers (like `servicing-service`) experience slight replication delays, requiring idempotency handling (`event_inbox` deduplication tables).
- **Operational Complexity**: Managing containerized multi-service deployments, local environment variables, and message broker infrastructure (LocalStack / AWS SNS/SQS) requires additional tooling and runbooks.