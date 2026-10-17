## Overview
This document defines the logical microservice components, data persistence tiers, messaging integrations, and inter-service communication patterns for the Enterprise Mortgage Platform.

---

## Application Architecture Diagram

```mermaid
graph TB
    %% Ingress & Consumer Layer
    subgraph Edge ["Ingress & Client Layer"]
        CLIENT[Portal UI / API Consumer\n(PowerShell / Postman / CLI)]
    end

    %% Microservices Layer
    subgraph CoreServices ["Core Microservices Layer"]
        MS[mortgage-service\n(Port 8080)]
        SS[servicing-service\n(Port 8081)]
        AS[mortgage-analytics-service\n(Port 8000 - Planned/M3)]
        AI[mortgage-knowledge-assistant\n(Port 8001 - Planned/M7)]
    end

    %% Messaging Integration Tier (Milestone 5)
    subgraph Integration ["Event-Driven Messaging Tier (SNS / SQS)"]
        SNS[AWS SNS Topic:\ncapstone-mortgage-lifecycle-dev]
        SQS[AWS SQS Queue:\ncapstone-mortgage-servicing-dev]
        DLQ[SQS Dead Letter Queue:\ncapstone-mortgage-servicing-dlq-dev]
        SNS -->|Dispatches Events| SQS
        SQS -.->|Failed Deliveries after Max Retries| DLQ
    end

    %% Persistence Layer
    subgraph Persistence ["Data Persistence Layer"]
        DB[(PostgreSQL Database\n:5432)]
        VDB[(Vector Store / Embeddings)]
        OBJ[(Cloud Object Storage\nS3 / Local Storage)]
    end

    %% Synchronous Interaction Paths (HTTP REST)
    CLIENT -->|HTTP REST /api/v1/borrowers| MS
    CLIENT -->|HTTP REST /api/v1/mortgages| MS
    CLIENT -->|HTTP REST /api/v1/mortgages/{id}/servicing-history| SS
    CLIENT -->|HTTP REST /api/v1/mortgages/{id}/delinquency| SS

    %% Data Store Interactions
    MS -->|JPA / JDBC SQL| DB
    SS -->|JPA / JDBC SQL| DB
    AS -->|Read-Only SQL| DB
    AI -->|Vector Indexing & Retrieval| VDB
    MS -.->|Document Uploads| OBJ

    %% Asynchronous Event Streams (Milestone 5)
    MS -->|Publish Lifecycle Events\n(MortgageCreated, PaymentReceived, PaymentMissed)| SNS
    SQS -->|Consume Events| SS