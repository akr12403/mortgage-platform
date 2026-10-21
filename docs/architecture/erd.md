# Entity Relationship Diagram

Physical model implemented by `database/migrations/001_core_schema.sql` (M2 baseline from the reference data model) plus `002_event_inbox_and_indexes.sql` and `003_idempotency_record.sql` (M5). Column details: [data-dictionary.md](./data-dictionary.md). Write ownership per table: [service-ownership-matrix.md](./service-ownership-matrix.md).

```mermaid
erDiagram
    BORROWER ||--o{ MORTGAGE : "has (borrower_id)"
    MORTGAGE ||--|| LOAN : "secured by (mortgage_id UNIQUE)"
    MORTGAGE ||--o{ PAYMENT : "receives (mortgage_id)"
    MORTGAGE ||--o{ SERVICING_HISTORY : "logs (mortgage_id)"
    MORTGAGE ||--o| DELINQUENCY : "may have (mortgage_id UNIQUE)"
    MORTGAGE ||--o{ DOCUMENT : "attaches (mortgage_id)"
    PAYMENT ||--o| IDEMPOTENCY_RECORD : "deduped by (payment_id)"

    BORROWER {
        uuid id PK
        varchar borrower_external_id UK "BOR-###"
        varchar first_name
        varchar last_name
        varchar email
        varchar phone
        date date_of_birth
        timestamptz created_at
    }
    MORTGAGE {
        uuid id PK
        varchar mortgage_external_id UK "MTG-####"
        uuid borrower_id FK
        varchar status "PENDING|ACTIVE|DELINQUENT|CLOSED"
        numeric original_amount "15,2"
        numeric outstanding_balance "15,2"
        date origination_date
        timestamptz created_at
    }
    LOAN {
        uuid id PK
        varchar loan_external_id UK "LOAN-####"
        uuid mortgage_id FK,UK
        numeric interest_rate "6,4"
        int term_months
        varchar underwriting_decision "PENDING|APPROVED|DECLINED"
        timestamptz created_at
    }
    PAYMENT {
        uuid id PK
        uuid mortgage_id FK
        date due_date
        date paid_date
        numeric amount "15,2"
        varchar status "SCHEDULED|POSTED|FAILED|REVERSED"
        timestamptz created_at
    }
    SERVICING_HISTORY {
        uuid id PK
        uuid mortgage_id FK
        timestamptz event_time
        varchar event_type
        text description
    }
    DELINQUENCY {
        uuid id PK
        uuid mortgage_id FK,UK
        date delinquent_since
        int days_past_due
        varchar severity "MODERATE|SEVERE|CRITICAL"
    }
    DOCUMENT {
        uuid id PK
        uuid mortgage_id FK
        varchar document_type
        varchar s3_key
        varchar file_name
        timestamptz created_at
    }
    IDEMPOTENCY_RECORD {
        varchar idempotency_key PK
        text request_fingerprint
        uuid payment_id FK
        timestamptz created_at
    }
    EVENT_INBOX {
        uuid event_id PK "eventId of consumed event"
        timestamptz processed_at
    }
```

## Cardinality and keys

| Relationship | Cardinality | Enforced by |
| --- | --- | --- |
| borrower → mortgage | 1 to 0..n | `mortgage.borrower_id` FK |
| mortgage → loan | 1 to 1 | `loan.mortgage_id` FK + UNIQUE |
| mortgage → payment | 1 to 0..n | `payment.mortgage_id` FK |
| mortgage → servicing_history | 1 to 0..n | `servicing_history.mortgage_id` FK |
| mortgage → delinquency | 1 to 0..1 (current snapshot) | `delinquency.mortgage_id` FK + UNIQUE (upserted from `LoanDelinquent`) |
| mortgage → document | 1 to 0..n | `document.mortgage_id` FK |
| payment → idempotency_record | 1 to 0..1 | `idempotency_record.payment_id` FK |
| event_inbox | standalone | PK `event_id` = dedupe key for the servicing consumer |

Every table uses a UUID surrogate PK (`gen_random_uuid()`, pgcrypto). Business keys (`borrower_external_id`, `mortgage_external_id`, `loan_external_id`) are UNIQUE and are the only identifiers exposed in APIs and events. Indexes: `idx_mortgage_borrower`, `idx_mortgage_status`, `idx_payment_mortgage_due`, `idx_servicing_mortgage_time`, `idx_document_mortgage` (rationale in [query-notes.md](./query-notes.md)).
