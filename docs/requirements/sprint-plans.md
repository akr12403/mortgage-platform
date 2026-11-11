# Sprint Plans (Sprint 1 & Sprint 2)

This document organizes the product backlog stories into strategic 2-week sprint executions for the capstone project.

---

## Sprint 1: Data Model & Foundational Read Paths
**Goal:** Establish baseline PostgreSQL relational schema, core entity CRUD operations, foundational data ingestion, and unblock Python analytics (M3) and Java backend services (M4).

### Prioritized User Stories

| Story ID | Summary | Persona | Target Milestone Unblocked |
| --- | --- | --- | --- |
| **US-BOR-001** | Create Borrower Profile | Loan Officer | M2, M4 |
| **US-BOR-002** | Retrieve Borrower Details | Servicing Agent | M2, M3, M4 |
| **US-MTG-001** | Create Mortgage Loan Record | Underwriter | M2, M4 |
| **US-MTG-002** | Get Mortgage Details | Servicing Agent | M2, M3, M4 |
| **US-SRV-001** | Retrieve Servicing History | Servicing Agent | M2, M4 |
| **US-PAY-002** | List Payment History | Borrower / Agent | M2, M3 |
| **US-DEL-001** | Get Delinquency Status | Risk Analyst | M2, M3 |
| **US-ANL-001** | Portfolio Summary Aggregation | Portfolio Manager | M3 |
| **US-SEC-001** | Deny Unauthorized Access | Compliance Officer | M6 |
| **US-OPS-001** | Health Check and DB Probe | DevSecOps Engineer | M2, M9 |

---

## Sprint 2: Core Write Paths, Servicing, Delinquency & AI Foundations
**Goal:** Implement transactional write paths (payment posting, status updates, loss mitigation flagging), business logic rules, and foundational AI document integration.

### Prioritized User Stories

| Story ID | Summary | Persona | Target Milestone Unblocked |
| --- | --- | --- | --- |
| **US-BOR-003** | Update Borrower Contact Info | Borrower / Support | M4 |
| **US-MTG-003** | Update Mortgage Status | Servicing Lead | M4 |
| **US-SRV-002** | Log Servicing Note or Action | Servicing Agent | M4 |
| **US-PAY-001** | Post Payment | Payment System | M4, M5 |
| **US-PAY-003** | Reverse Erroneous Payment | Payment Specialist | M4 |
| **US-DEL-002** | Flag Mortgage for Loss Mitigation | Loss Mitigation Specialist | M4 |
| **US-DEL-003** | Calculate Portfolio Delinquency Rate | Risk Manager | M3, M4 |
| **US-ANL-002** | Generate Monthly Performance Report | Secondary Market Analyst | M3 |
| **US-SEC-002** | Enforce Role-Based Access Control | Compliance Officer | M6 |
| **US-AI-001** | Grounded Q&A over Mortgage Docs | Loan Officer | M7 |
| **US-AI-002** | Automated Document Extraction | Underwriter | M7 |
| **US-OPS-002** | Structured Audit Logging | Compliance Officer | M6, M9 |