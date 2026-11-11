# ADR-001: Servicing Service Data Ownership and Persistence Strategy

* **Status**: Accepted — amended by [ADR-002](./ADR-002-microservices-decomposition.md) (M5): `servicing_history` and `delinquency` are now written only by `servicing-service`, projected from lifecycle events; `mortgage-service` no longer writes them.
* **Context**: Task 4.3 – Microservice Architecture & Separation
* **Date**: October 12, 2026

## Context & Problem Statement
With the introduction of the new `servicing-service` microservice operating on port `8081`, we must determine how the service accesses and manages persistence data, specifically concerning audit logs and mortgage histories (`servicing_history`). We need to balance architectural isolation with transactional simplicity and minimal network overhead.

## Considered Options
1. **Option A: Completely Independent Database & Schema per Service (Shared-Nothing / API Calls)**
   - The servicing service runs its own isolated database and calls the `mortgage-service` via REST APIs to resolve mortgage information.
   - *Pros*: True database decoupling; strict domain boundary ownership.
   - *Cons*: Introduces network latency, potential distributed transaction complexity, and data duplication for high-frequency audit logs.

2. **Option B: Shared Database with Logical Separation (Shared Database / Dedicated Schema or Tables)**
   - The servicing service connects to a dedicated development database (`servicing_intel_dev`) while sharing the underlying table structures (`servicing_history`) populated by the core `mortgage-service` transactions.
   - *Pros*: Direct, high-performance querying of historical events by `mortgage_id`; straightforward repository mapping without complex inter-service HTTP orchestration for read-heavy auditing.
   - *Cons*: Tighter coupling at the database level.

## Decision
We chose **Option B (Shared Database with Logical Separation / Dedicated Service Connection)** for the initial capstone architecture. 

The `servicing-service` operates as an independent microservice container on port `8081` with its own application context, repository layers, and dedicated database connection profile (`servicing_intel_dev`), while logically referencing the shared `servicing_history` data domain. This allows us to fulfill audit retrieval (`GET /api/v1/mortgages/{id}/servicing-history`) and delinquency analysis (`GET /api/v1/mortgages/{id}/delinquency`) with high efficiency and minimal latency.

## Consequences
* **Positive**: Fast query execution for audit histories and delinquency checks without cross-service cascading HTTP calls. Clean separation of concerns in the application codebase (`servicing-service` vs. `mortgage-service`).
* **Negative / Trade-off**: Database schema changes affecting `servicing_history` must be coordinated across services.