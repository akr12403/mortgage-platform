# Product Backlog & User Stories

This document defines the complete set of INVEST-style user stories across all system epics. Each story includes Given/When/Then acceptance criteria and maps directly to a target persona defined in [`personas.md`](./personas.md).

---

## Epic 1: Borrower Management

### US-BOR-001: Create Borrower Profile
- **Persona:** Loan Officer / Underwriter
- **Description:** As a loan officer, I want to create a new borrower profile in the platform so that credit and underwriting activities can be tied to a unique individual.
- **Acceptance Criteria:**
  - **Given** valid borrower details (first name, last name, email, SSN/tax ID, credit score),
  - **When** the creation request is submitted,
  - **Then** the system creates a borrower record with a unique `borrower_id` and returns a `201 Created` status.

### US-BOR-002: Retrieve Borrower Details
- **Persona:** Loan Officer / Servicing Agent
- **Description:** As a servicing agent, I want to retrieve a borrower's complete details by their ID so that I can review contact and financial metadata.
- **Acceptance Criteria:**
  - **Given** a valid `borrower_id`,
  - **When** the retrieval endpoint is queried,
  - **Then** the system returns borrower details including active loans and contact information with a `200 OK` status.

### US-BOR-003: Update Borrower Contact Information
- **Persona:** Borrower / Customer Support Representative
- **Description:** As a borrower, I want to update my email address and primary phone number so that I receive timely loan notifications.
- **Acceptance Criteria:**
  - **Given** an existing `borrower_id` and updated contact payload,
  - **When** the update request is sent,
  - **Then** the record updates successfully and an audit log event is recorded.

---

## Epic 2: Mortgage Management

### US-MTG-001: Create Mortgage Loan Record
- **Persona:** Underwriter / Origination Specialist
- **Description:** As an underwriter, I want to register a newly originated mortgage loan tied to an existing borrower so that servicing and analytics can track it.
- **Acceptance Criteria:**
  - **Given** a valid `borrower_id`, principal amount, interest rate, term, and property address,
  - **When** the mortgage creation request is issued,
  - **Then** the system assigns a formatted `mortgage_external_id` (e.g., `MTG-1001`), sets the status to `ACTIVE`, and returns `201 Created`.

### US-MTG-002: Get Mortgage Details
- **Persona:** Portfolio Manager / Servicing Agent
- **Description:** As a servicing agent, I want to look up a mortgage loan by its external ID so that I can inspect balance, interest rate, and status details.
- **Acceptance Criteria:**
  - **Given** a valid `mortgage_external_id` (e.g., `MTG-1001`),
  - **When** requested via the lookup API,
  - **Then** the system returns full loan metadata including current unpaid principal balance (UPB) and status.

### US-MTG-003: Update Mortgage Status
- **Persona:** Secondary Market Analyst / Servicing Lead
- **Description:** As a servicing lead, I want to transition a mortgage status (e.g., `ACTIVE`, `DELINQUENT`, `PAID_IN_FULL`) so that downstream workflows adjust accordingly.
- **Acceptance Criteria:**
  - **Given** a valid mortgage ID and target status,
  - **When** the status update command is executed,
  - **Then** the system validates state machine rules and records the new status along with a timestamp.

---

## Epic 3: Loan Servicing

### US-SRV-001: Retrieve Servicing History
- **Persona:** Servicing Agent
- **Description:** As a servicing agent, I want to retrieve mortgage servicing history so that I can understand the current status and chronological events of a loan.
- **Acceptance Criteria:**
  - **Given** a valid mortgage ID,
  - **When** servicing history is requested,
  - **Then** the system returns servicing events in reverse chronological order.

### US-SRV-002: Log Servicing Note or Action
- **Persona:** Servicing Agent / Loss Mitigation Specialist
- **Description:** As a servicing agent, I want to log a servicing action or note against a mortgage so that team members can track borrower interactions.
- **Acceptance Criteria:**
  - **Given** a valid mortgage ID, agent user ID, and non-empty note text,
  - **When** the note is submitted,
  - **Then** a new servicing history entry is saved with an automated timestamp.

---

## Epic 4: Payment Processing

### US-PAY-001: Post Payment
- **Persona:** Servicing Agent / Payment Processing System
- **Description:** As a servicing system, I want to post a payment against a mortgage so that principal, interest, and escrow balances update accurately.
- **Acceptance Criteria:**
  - **Given** a valid mortgage ID, payment amount, and payment date,
  - **When** payment posting is processed,
  - **Then** the system calculates principal and interest breakdown, updates loan UPB, and records a transaction log.

### US-PAY-002: List Payment History
- **Persona:** Borrower / Servicing Agent
- **Description:** As a borrower, I want to view all past payments for my mortgage so that I can confirm receipt and verify payment history.
- **Acceptance Criteria:**
  - **Given** a valid `mortgage_external_id`,
  - **When** payment history is requested,
  - **Then** all historic payment transactions are returned paginated by date.

### US-PAY-003: Reverse Erroneous Payment
- **Persona:** Payment Operations Specialist
- **Description:** As a payment operations specialist, I want to reverse a duplicate or erroneous payment entry so that loan balances remain accounting-compliant.
- **Acceptance Criteria:**
  - **Given** a valid `payment_id` and authorization flag,
  - **When** a reversal request is processed,
  - **Then** a compensating transaction is recorded and current balance is recalculated.

---

## Epic 5: Delinquency & Loss Mitigation

### US-DEL-001: Get Delinquency Status
- **Persona:** Risk Analyst / Loss Mitigation Specialist
- **Description:** As a risk analyst, I want to check the delinquency status and days past due (DPD) for a mortgage so that delinquent accounts can be prioritized.
- **Acceptance Criteria:**
  - **Given** a valid mortgage ID (e.g., `MTG-1002`),
  - **When** delinquency status is queried,
  - **Then** the system returns current DPD, missed payment count, and risk bucket (e.g., 30-day, 60-day, 90-day+).

### US-DEL-002: Flag Mortgage for Loss Mitigation
- **Persona:** Loss Mitigation Specialist
- **Description:** As a loss mitigation specialist, I want to flag a delinquent mortgage for a workout plan or forbearance so that foreclosure actions are paused.
- **Acceptance Criteria:**
  - **Given** a mortgage with DPD ≥ 60 days,
  - **When** flagged for loss mitigation,
  - **Then** the system updates loan flag status and notifies the risk team.

### US-DEL-003: Calculate Portfolio Delinquency Rate
- **Persona:** Executive / Portfolio Risk Manager
- **Description:** As a portfolio risk manager, I want to calculate overall delinquency percentages across all active loans so that macro credit trends are monitored.
- **Acceptance Criteria:**
  - **Given** active mortgage portfolio records,
  - **When** the delinquency calculation executes,
  - **Then** total delinquent UPB and count are aggregated against total active portfolio metrics.

---

## Epic 6: Analytics & Reporting

### US-ANL-001: Portfolio Summary Aggregation
- **Persona:** Portfolio Risk Manager / Executive
- **Description:** As a portfolio manager, I want an aggregated summary of total loans, total UPB, and average interest rate so that executive dashboards reflect real-time risk.
- **Acceptance Criteria:**
  - **Given** existing mortgage dataset in PostgreSQL,
  - **When** the summary endpoint or analytics query is executed,
  - **Then** total active loan count, total UPB, and weighted average interest rate are returned within SLA (<2 seconds).

### US-ANL-002: Generate Monthly Performance Report
- **Persona:** Secondary Market Analyst
- **Description:** As a secondary market analyst, I want to export monthly cashflow and delinquency breakdown reports so that investor reporting requirements are met.
- **Acceptance Criteria:**
  - **Given** a specified month and year,
  - **When** report generation is triggered,
  - **Then** a structured summary JSON/CSV output is generated containing total collections and default metrics.

---

## Epic 7: Security & Access Control

### US-SEC-001: Deny Unauthorized Access
- **Persona:** Compliance & Security Officer
- **Description:** As a security officer, I want unauthenticated or unauthorized requests to be denied so that sensitive borrower financial data remains protected.
- **Acceptance Criteria:**
  - **Given** an HTTP request missing or containing an invalid JWT bearer token,
  - **When** accessing any protected endpoint (e.g., `/api/v1/borrowers`),
  - **Then** the system responds with `401 Unauthorized` or `403 Forbidden` and logs a security event.

### US-SEC-002: Enforce Role-Based Access Control (RBAC)
- **Persona:** Compliance & Security Officer
- **Description:** As a compliance officer, I want servicing agents restricted from executing executive risk adjustments so that segregation of duties is enforced.
- **Acceptance Criteria:**
  - **Given** a user authenticated under the `SERVICING_AGENT` role,
  - **When** attempting to invoke executive management endpoints,
  - **Then** the request is rejected with `403 Forbidden`.

---

## Epic 8: AI & Document Intelligence Assistant

### US-AI-001: Grounded Q&A over Mortgage Documents
- **Persona:** Loan Officer / Servicing Agent
- **Description:** As a loan officer, I want to ask questions about borrower document disclosures and receive AI responses grounded strictly in uploaded document text so that information retrieval is accelerated without hallucination.
- **Acceptance Criteria:**
  - **Given** an indexed mortgage document (e.g., tax return or paystub) and a query prompt,
  - **When** submitted to the AI assistant endpoint,
  - **Then** the system returns an answer with source citations referencing exact document sections.

### US-AI-002: Automated Document Extraction
- **Persona:** Underwriter
- **Description:** As an underwriter, I want automatic key-value extraction (gross income, employer name) from uploaded PDF documents so that manual data entry errors are reduced.
- **Acceptance Criteria:**
  - **Given** a newly uploaded income document PDF,
  - **When** document processing finishes,
  - **Then** extracted fields are structured in JSON format and stored with high confidence scores.

---

## Epic 9: System & Operations

### US-OPS-001: Health Check and DB Probe
- **Persona:** DevSecOps Engineer
- **Description:** As an operations engineer, I want health check endpoints that verify application and database connectivity so that container orchestrators can monitor system status.
- **Acceptance Criteria:**
  - **Given** running service instances,
  - **When** `/health` is probed,
  - **Then** the system checks PostgreSQL connection state and returns HTTP `200 OK` with JSON `{"status": "UP"}`.

### US-OPS-002: Structured Audit Logging
- **Persona:** Compliance & Security Officer
- **Description:** As a compliance officer, I want all financial state mutations (payments, status updates) logged in structured JSON so that audit trails are maintained for regulatory review.
- **Acceptance Criteria:**
  - **Given** any write operation on mortgage records,
  - **When** the transaction completes,
  - **Then** a structured JSON log containing `timestamp`, `user_id`, `action`, and `target_id` is emitted.