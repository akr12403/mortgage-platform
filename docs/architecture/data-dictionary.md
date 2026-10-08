This data dictionary documents the PostgreSQL physical database schema for the Secondary Mortgage Intelligence Platform. It defines table columns, primary/foreign keys, nullability, constraints, cardinalities, and performance index recommendations.

---

## Table 1: `borrowers`

Stores borrower profile information, contact metadata, and credit baseline scores.

- **Primary Key:** `id` (`UUID`)
- **Cardinality:** 1 Borrower to `N` Loans

| Column Name | Data Type | Nullable | Constraints | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | `PRIMARY KEY`, Default `gen_random_uuid()` | Internal surrogate key. |
| `borrower_external_id` | `VARCHAR(32)` | No | `UNIQUE`, `NOT NULL` | Business ID format (e.g., `BOR-1001`). |
| `first_name` | `VARCHAR(64)` | No | `NOT NULL` | Borrower given name. |
| `last_name` | `VARCHAR(64)` | No | `NOT NULL` | Borrower surname. |
| `email` | `VARCHAR(128)` | No | `NOT NULL`, `CHECK (email LIKE '%@%')` | Primary email contact. |
| `phone` | `VARCHAR(20)` | Yes | — | Contact telephone number. |
| `tax_id_hash` | `VARCHAR(64)` | No | `NOT NULL` | SHA-256 hashed SSN/ITIN for compliance. |
| `credit_score` | `INTEGER` | No | `CHECK (credit_score BETWEEN 300 AND 850)` | FICO score baseline. |
| `created_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Record modification timestamp. |

### Recommended Indexes
- `idx_borrower_external_id`: Unique B-Tree index on `borrower_external_id` for fast API lookups.
- `idx_borrower_email`: B-Tree index on `email`.

---

## Table 2: `loans`

Stores origination data and contract terms for mortgage applications.

- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** `borrower_id` $\rightarrow$ `borrowers(id)`
- **Cardinality:** 1 Loan belongs to 1 Borrower; 1 Loan maps to 1 Mortgage.

| Column Name | Data Type | Nullable | Constraints | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | `PRIMARY KEY`, Default `gen_random_uuid()` | Internal surrogate key. |
| `loan_external_id` | `VARCHAR(32)` | No | `UNIQUE`, `NOT NULL` | Business ID format (e.g., `LN-9001`). |
| `borrower_id` | `UUID` | No | `REFERENCES borrowers(id) ON DELETE RESTRICT` | FK to associated borrower. |
| `origination_principal`| `NUMERIC(12,2)`| No | `CHECK (origination_principal > 0)` | Total loan amount at closing. |
| `interest_rate` | `NUMERIC(5,4)` | No | `CHECK (interest_rate > 0)` | Annual interest rate (e.g. 0.0650 for 6.5%). |
| `term_months` | `INTEGER` | No | `CHECK (term_months IN (180, 240, 360))` | Loan term length in months (15, 20, 30 yr). |
| `origination_date` | `TIMESTAMPTZ` | No | `NOT NULL` | Loan origination closing date. |
| `property_address` | `TEXT` | No | `NOT NULL` | Physical property street address. |
| `property_type` | `VARCHAR(32)` | No | `CHECK (property_type IN ('SINGLE_FAMILY', 'CONDO', 'TOWNHOUSE', 'MULTI_FAMILY'))` | Property classification. |
| `created_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Record creation timestamp. |

### Recommended Indexes
- `idx_loan_borrower_id`: B-Tree index on `borrower_id` to optimize borrower-to-loan join operations.
- `idx_loan_external_id`: Unique B-Tree index on `loan_external_id`.

---

## Table 3: `mortgages`

Stores active mortgage servicing status, current unpaid principal balance (UPB), and current interest rate.

- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** `loan_id` $\rightarrow$ `loans(id)`, `borrower_id` $\rightarrow$ `borrowers(id)`
- **Cardinality:** 1 Mortgage to `N` Payments / Servicing / Delinquency / Documents.

| Column Name | Data Type | Nullable | Constraints | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | `PRIMARY KEY`, Default `gen_random_uuid()` | Internal surrogate key. |
| `mortgage_external_id` | `VARCHAR(32)` | No | `UNIQUE`, `NOT NULL` | Business ID format (e.g., `MTG-1001`). |
| `loan_id` | `UUID` | No | `UNIQUE`, `REFERENCES loans(id) ON DELETE RESTRICT` | FK linking origination loan. |
| `borrower_id` | `UUID` | No | `REFERENCES borrowers(id) ON DELETE RESTRICT` | FK linking borrower profile. |
| `current_unpaid_principal_balance` | `NUMERIC(12,2)` | No | `CHECK (current_unpaid_principal_balance >= 0)` | Current unpaid principal balance (UPB). |
| `current_interest_rate` | `NUMERIC(5,4)` | No | `CHECK (current_interest_rate > 0)` | Current applicable interest rate. |
| `status` | `VARCHAR(32)` | No | `CHECK (status IN ('ACTIVE', 'DELINQUENT', 'PAID_IN_FULL', 'DEFAULT', 'FORECLOSURE'))` | Current servicing status. |
| `maturity_date` | `DATE` | No | `NOT NULL` | Loan maturity date. |
| `created_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Record update timestamp. |

### Recommended Indexes
- `idx_mortgage_external_id`: Unique B-Tree index on `mortgage_external_id` (Primary search target).
- `idx_mortgage_borrower_id`: B-Tree index on `borrower_id`.
- `idx_mortgage_status`: B-Tree index on `status` to unblock analytics queries on active/delinquent subsets.

---

## Table 4: `payments`

Stores historic ledger payments processed against mortgage balances.

- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** `mortgage_id` $\rightarrow$ `mortgages(id)`
- **Cardinality:** `N` Payments belong to 1 Mortgage.

| Column Name | Data Type | Nullable | Constraints | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | `PRIMARY KEY`, Default `gen_random_uuid()` | Internal surrogate key. |
| `payment_external_id` | `VARCHAR(32)` | No | `UNIQUE`, `NOT NULL` | Business ID format (e.g., `PAY-5001`). |
| `mortgage_id` | `UUID` | No | `REFERENCES mortgages(id) ON DELETE CASCADE` | FK linking target mortgage. |
| `payment_amount` | `NUMERIC(10,2)`| No | `CHECK (payment_amount > 0)` | Total payment amount posted. |
| `principal_portion` | `NUMERIC(10,2)`| No | `CHECK (principal_portion >= 0)` | Portion applied to principal balance. |
| `interest_portion` | `NUMERIC(10,2)`| No | `CHECK (interest_portion >= 0)` | Portion applied to interest balance. |
| `escrow_portion` | `NUMERIC(10,2)`| No | `CHECK (escrow_portion >= 0)` | Portion applied to escrow account. |
| `payment_date` | `DATE` | No | `NOT NULL` | Transaction posting date. |
| `payment_status` | `VARCHAR(32)` | No | `CHECK (payment_status IN ('POSTED', 'REVERSED', 'PENDING'))` | Current status of payment entry. |
| `processed_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | System processing timestamp. |

### Recommended Indexes
- `idx_payment_mortgage_date`: Composite B-Tree index on `(mortgage_id, payment_date DESC)` for fast historical ledger lookups.
- `idx_payment_external_id`: Unique B-Tree index on `payment_external_id`.

---

## Table 5: `servicing_history`

Audit trail recording agent interactions, notes, and workout actions on loans.

- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** `mortgage_id` $\rightarrow$ `mortgages(id)`
- **Cardinality:** `N` History events belong to 1 Mortgage.

| Column Name | Data Type | Nullable | Constraints | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | `PRIMARY KEY`, Default `gen_random_uuid()` | Internal surrogate key. |
| `mortgage_id` | `UUID` | No | `REFERENCES mortgages(id) ON DELETE CASCADE` | FK linking target mortgage. |
| `event_type` | `VARCHAR(32)` | No | `CHECK (event_type IN ('NOTE', 'STATUS_CHANGE', 'PAYMENT_POST', 'WORKOUT', 'DELINQUENCY_NOTICE'))` | Event classification. |
| `description` | `TEXT` | No | `NOT NULL` | Detailed event log or servicing agent note. |
| `agent_id` | `VARCHAR(64)` | No | `NOT NULL` | User ID or agent who performed the action. |
| `recorded_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Event timestamp. |

### Recommended Indexes
- `idx_servicing_history_mortgage`: B-Tree index on `(mortgage_id, recorded_at DESC)` for chronological servicing logs.

---

## Table 6: `delinquency`

Tracks periodic delinquency evaluations, days past due (DPD), and loss mitigation status.

- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** `mortgage_id` $\rightarrow$ `mortgages(id)`
- **Cardinality:** `N` Delinquency snapshots belong to 1 Mortgage.

| Column Name | Data Type | Nullable | Constraints | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | `PRIMARY KEY`, Default `gen_random_uuid()` | Internal surrogate key. |
| `mortgage_id` | `UUID` | No | `REFERENCES mortgages(id) ON DELETE CASCADE` | FK linking target mortgage. |
| `days_past_due` | `INTEGER` | No | `CHECK (days_past_due >= 0)` | Calculated days past due (DPD). |
| `delinquent_amount` | `NUMERIC(10,2)`| No | `CHECK (delinquent_amount >= 0)` | Total delinquent payment amount overdue. |
| `risk_bucket` | `VARCHAR(32)` | No | `CHECK (risk_bucket IN ('CURRENT', '30_DAYS', '60_DAYS', '90_DAYS_PLUS', 'CRITICAL'))` | Portfolio risk category. |
| `in_loss_mitigation`| `BOOLEAN` | No | `DEFAULT FALSE` | Flag indicating active workout/forbearance. |
| `evaluation_date` | `DATE` | No | `NOT NULL` | Snapshot evaluation date. |
| `created_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Snapshot creation timestamp. |

### Recommended Indexes
- `idx_delinquency_mortgage_eval`: Composite index on `(mortgage_id, evaluation_date DESC)`.
- `idx_delinquency_risk`: Index on `(risk_bucket, days_past_due)` for high-risk portfolio reports.

---

## Table 7: `documents`

Stores document metadata, mime types, and object storage links for borrower uploads.

- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** `mortgage_id` $\rightarrow$ `mortgages(id)`
- **Cardinality:** `N` Documents attached to 1 Mortgage.

| Column Name | Data Type | Nullable | Constraints | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | `PRIMARY KEY`, Default `gen_random_uuid()` | Internal surrogate key. |
| `document_external_id` | `VARCHAR(32)` | No | `UNIQUE`, `NOT NULL` | Business ID format (e.g., `DOC-8001`). |
| `mortgage_id` | `UUID` | No | `REFERENCES mortgages(id) ON DELETE CASCADE` | FK linking target mortgage. |
| `document_type` | `VARCHAR(32)` | No | `CHECK (document_type IN ('PAYSTUB', 'W2', 'TAX_RETURN', 'APPRAISAL', 'CLOSING_DISCLOSURE'))` | Document classification. |
| `file_name` | `VARCHAR(255)`| No | `NOT NULL` | Original uploaded file name. |
| `storage_path` | `TEXT` | No | `NOT NULL` | S3 / local object store bucket path. |
| `mime_type` | `VARCHAR(64)` | No | `NOT NULL` | MIME type (e.g. `application/pdf`). |
| `file_size_bytes` | `BIGINT` | No | `CHECK (file_size_bytes > 0)` | File size in bytes. |
| `uploaded_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | File upload timestamp. |

### Recommended Indexes
- `idx_documents_mortgage_id`: B-Tree index on `mortgage_id`.
- `idx_documents_external_id`: Unique index on `document_external_id`.