# Service Ownership Matrix

This document distinguishes write ownership from read access. The canonical schema is defined in `database/migrations/001_core_schema.sql`; UUIDs are internal keys and `BOR-*`, `MTG-*`, and `LOAN-*` are external business identifiers.

| Service Name | Port | Owned Database Tables / Storage | Owned REST APIs | Events Produced | Events Consumed |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`mortgage-service`** | `8080` | Writes `borrower`, `mortgage`, `loan`, `payment`, and synchronous payment history | • `POST /api/v1/borrowers`<br>• `POST /api/v1/mortgages`<br>• `GET /api/v1/mortgages/{mortgageExternalId}`<br>• Payment and borrower-mortgage reads | • `MortgageCreated`<br>• `LoanApproved`<br>• `PaymentReceived`<br>• `PaymentMissed` | None |
| **`servicing-service`** | `8081` | Writes consumed-event `servicing_history` rows and `event_inbox` deduplication records | • `GET /api/v1/mortgages/{mortgageExternalId}/servicing-history`<br>• `GET /api/v1/mortgages/{mortgageExternalId}/delinquency`<br>• `POST /api/v1/mortgages/{mortgageExternalId}/servicing-events` | None currently wired | `MortgageCreated`, `LoanApproved`, `PaymentReceived`, `PaymentMissed`, `LoanDelinquent` |
| **`mortgage-analytics-service`** | `8000` | Reads canonical PostgreSQL tables; writes document metadata for the M3 upload workflow | `/health`, portfolio summary, delinquency, borrower-risk, payment-trend, document-upload endpoints | None | None; analytics is not currently an SQS consumer |
| **`mortgage-knowledge-assistant`** | `8001` | Vector Store (Embeddings), Cloud Object Storage (S3 / Local S3) | • `/health`<br>• Document query & RAG search endpoints | *None* | *None* |

---

## Domain Boundary Guidelines & Rules

1. **Current capstone persistence**:
   - Local Java and Python services use the shared canonical PostgreSQL schema. This is an educational shared-database arrangement, not physical database isolation.
   - Internal relationships use UUIDs. Never derive database IDs by stripping digits from external business IDs.

2. **Event-driven projection**:
   - `mortgage-service` publishes mortgage, approval, and payment lifecycle events.
   - `servicing-service` consumes them to maintain servicing history. Analytics currently reads PostgreSQL; event consumption for analytics remains future work.