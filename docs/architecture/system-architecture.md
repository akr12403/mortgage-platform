# High-Level System Architecture

## 1. Executive Summary
The Enterprise Mortgage Platform is designed as a cloud-native, microservice-based system supporting end-to-end mortgage origination, loan servicing, real-time analytics, and AI-assisted borrower support.

## 2. High-Level Architecture Diagram

```mermaid
graph TB
    %% Client Layer
    subgraph Clients ["Client Layer"]
        UI[Web App / Mobile UI]
    end

    %% Gateway Layer
    subgraph Edge ["Edge & Security"]
        GW[API Gateway / Ingress Router]
    end

    %% Microservices Layer
    subgraph Services ["Core Services Layer"]
        MS[Mortgage Service\n:8080]
        SS[Servicing Service\n:8081]
        AS[Mortgage Analytics Service\n:8000]
        AI[Mortgage Knowledge Assistant\n:8001]
    end

    %% Messaging / Integration
    subgraph EventBus ["Event Streaming"]
        MB[Message Broker / Event Bus]
    end

    %% Data Layer
    subgraph DataTier ["Data Persistence Layer"]
        DB[(PostgreSQL Database\n:5432)]
        VDB[(Vector Store / Embeddings)]
    end

    %% Relationships & Protocols
    UI -->|HTTPS / REST| GW
    GW -->|HTTP / REST| MS
    GW -->|HTTP / REST| SS
    GW -->|HTTP / REST| AS
    GW -->|HTTP / WebSockets| AI

    MS -->|JDBC / SQL| DB
    SS -->|JDBC / SQL| DB
    AS -->|Read SQL| DB
    AI -->|Vector Queries| VDB

    MS -.->|Publish Loan Events| MB
    SS -.->|Publish Payment Events| MB
    MB -.->|Consume Events| AS