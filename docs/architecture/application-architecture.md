## Overview
This document defines the logical microservice components, data persistence tiers, messaging integrations, and inter-service communication patterns for the Enterprise Mortgage Platform.

## Application Architecture Diagram

```mermaid
graph TB
    %% Ingress & Consumer Layer
    subgraph Edge ["Ingress & Client Layer"]
        CLIENT[Portal UI / API Consumer\n(Web / CLI Placeholder)]
        GW[API Gateway / Ingress Router\n:8080]
    end

    %% Microservices Layer
    subgraph CoreServices ["Core Services Layer"]
        MS[Mortgage Service\n:8080]
        SS[Servicing Service\n:8081]
        AS[Mortgage Analytics Service\n:8082]
        AI[Mortgage Knowledge Assistant\n:8083]
    end

    %% Messaging Integration Placeholder
    subgraph Integration ["Event Streaming Tier"]
        MB[Message Broker / Event Bus\n(RabbitMQ / Kafka Placeholder)]
    end

    %% Persistence Layer
    subgraph Persistence ["Data Persistence Layer"]
        DB[(PostgreSQL Database\n:5432)]
        VDB[(Vector Store / Embeddings)]
        OBJ[(Cloud Object Storage\nS3 / Local Storage)]
    end

    %% Interaction Paths (Synchronous REST)
    CLIENT -->|HTTPS / REST| GW
    GW -->|HTTP / REST| MS
    GW -->|HTTP / REST| SS
    GW -->|HTTP / REST| AS
    GW -->|HTTP / REST| AI

    %% Data Store Interactions
    MS -->|JDBC / SQL| DB
    SS -->|JDBC / SQL| DB
    AS -->|Read-Only SQL| DB
    AI -->|Vector Indexing & Retrieval| VDB
    MS -.->|Document Upload Path| OBJ

    %% Asynchronous Event Streams (Planned)
    MS -.->|Publish Loan Events| MB
    SS -.->|Publish Payment Events| MB
    MB -.->|Consume Events| AS