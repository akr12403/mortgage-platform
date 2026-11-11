# Application Architecture

Logical services, data ownership, and communication paths for the platform as of **Milestone 5**. Ownership details: [service-ownership-matrix.md](./service-ownership-matrix.md). Decision record: [ADR-002](../adr/ADR-002-microservices-decomposition.md). Events: [event-catalog.md](./event-catalog.md).

## Service boundary diagram

```mermaid
flowchart LR
    CLIENT["API consumer<br/>(curl / Postman / UI in M6)"]

    subgraph ORIG["Origination & Payments context"]
        MS["mortgage-service :8080<br/>Java / Spring Boot"]
    end

    subgraph SERV["Servicing context"]
        SS["servicing-service :8081<br/>Java / Spring Boot"]
    end

    subgraph ANLY["Analytics context"]
        AS["mortgage-analytics-service :8000<br/>Python / FastAPI"]
    end

    subgraph MSG["Messaging (LocalStack locally, AWS sandbox later)"]
        SNS(["SNS capstone-mortgage-lifecycle-dev"])
        QS[["SQS capstone-mortgage-servicing-dev"]]
        QA[["SQS capstone-mortgage-analytics-dev"]]
        DLQS[["DLQ capstone-mortgage-servicing-dlq-dev"]]
        DLQA[["DLQ capstone-mortgage-analytics-dlq-dev"]]
    end

    subgraph DB["PostgreSQL mortgage_intel (single writer per table)"]
        T1[("borrower · mortgage · loan · payment · idempotency_record")]
        T2[("servicing_history · delinquency · event_inbox")]
        T3[("document")]
    end

    CLIENT -->|"REST /api/v1/borrowers, /mortgages, /payments,<br/>/underwriting-decision, /delinquency-evaluations"| MS
    CLIENT -->|"REST /api/v1/mortgages/{id}/servicing-history, /delinquency"| SS
    CLIENT -->|"REST /api/v1/analytics/*, /documents/upload"| AS

    MS -->|writes| T1
    MS -->|"publish after commit:<br/>MortgageCreated, LoanApproved,<br/>PaymentReceived, PaymentMissed, LoanDelinquent"| SNS
    SNS --> QS
    SNS --> QA
    QS -->|poll, ack after commit| SS
    QA -->|poll, refresh snapshot| AS
    QS -.->|"after 3 receives"| DLQS
    QA -.->|"after 3 receives"| DLQA

    SS -->|writes| T2
    SS -.->|"reads mortgage (ID lookup)"| T1
    AS -->|writes| T3
    AS -.->|"reads (reporting)"| T1
    AS -.->|"reads delinquency"| T2
```

Solid arrows are writes or calls. Dotted arrows are read-only access or redrive.

## Boundaries in one line each

- **mortgage-service** decides: it creates mortgages, records underwriting decisions, posts payments, and applies the 30-day delinquency rule. It is the only event publisher.
- **servicing-service** records: it turns events into the servicing history and the delinquency snapshot, and serves them.
- **analytics-service** reports: it reads canonical tables for portfolio metrics and refreshes a portfolio snapshot when events arrive.

## Cyclic dependencies

There are none. The only runtime coupling between services is the one-way event flow from mortgage-service to the consumers. No service calls another's REST API, and consumers never publish to the lifecycle topic. The M4 cross-writes (mortgage-service writing `servicing_history` and `delinquency`) were removed in M5. Shared-database **reads** remain and are listed in the ownership matrix and ADR-002.

## Request → event → projection example (payment)

1. `POST /api/v1/mortgages/MTG-1001/payments` with `X-Correlation-Id: 7c9e…` → mortgage-service saves the `payment`, reduces `mortgage.outstanding_balance`, and commits.
2. After commit it publishes `PaymentReceived` (`correlationId` = `7c9e…`) to SNS.
3. SNS delivers to both queues. servicing-service writes `servicing_history(PAYMENT_POSTED)` and `event_inbox` in one transaction, then deletes the message. analytics-service refreshes its snapshot.
4. On failure the message stays in the queue, is retried after 30 s, and after 3 receives moves to the DLQ. The final attempt is logged at ERROR.
