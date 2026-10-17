# Service Ownership Matrix

This document defines the clear domain boundaries, database table ownership, exposed REST APIs, and asynchronous event streams managed by each microservice in the Enterprise Mortgage Platform.

| Service Name | Port | Owned Database Tables / Storage | Owned REST APIs | Events Produced | Events Consumed |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`mortgage-service`** | `8080` | `borrowers`, `mortgages`, `payments`, event inbox tables | • `POST /api/v1/borrowers`<br>• `POST /api/v1/mortgages`<br>• `GET /api/v1/mortgages/{id}`<br>• `POST /api/v1/mortgages/{id}/payments` | • `MortgageCreated`<br>• `LoanApproved`<br>• `PaymentReceived`<br>• `PaymentMissed` | *None* (Producer) |
| **`servicing-service`** | `8081` | `servicing_history`, event inbox / deduplication store | • `GET /api/v1/mortgages/{id}/servicing-history`<br>• `GET /api/v1/mortgages/{id}/delinquency`<br>• `POST /api/v1/mortgages/{id}/servicing-events` | • `LoanDelinquent` | • `MortgageCreated`<br>• `PaymentReceived`<br>• `PaymentMissed`<br>• `LoanDelinquent` |
| **`mortgage-analytics-service`** | `8000` | Read-only operational views / data lake extracts | • `/health`<br>• Portfolio analytics & risk reporting endpoints | *None* | • Lifecycle event feeds (for metric aggregation) |
| **`mortgage-knowledge-assistant`** | `8001` | Vector Store (Embeddings), Cloud Object Storage (S3 / Local S3) | • `/health`<br>• Document query & RAG search endpoints | *None* | *None* |

---

## Domain Boundary Guidelines & Rules

1. **Strict Database Isolation**: 
   - No microservice is permitted to execute direct SQL queries or write operations against tables owned by another microservice. 
   - Cross-domain data synchronization must occur strictly via **asynchronous event consumption (SNS/SQS)** or contract-backed **REST queries**.

2. **Event-Driven Decoupling**:
   - `mortgage-service` acts as the primary publisher for origination and transactional state changes.
   - `servicing-service` consumes these messages to maintain an immutable audit trail (`servicing_history`) and compute real-time risk/delinquency metrics independently.