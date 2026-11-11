# Mortgage Lifecycle Business Flow

## 1. Executive Summary
This document establishes the official end-to-end business flow and mortgage lifecycle for the Enterprise Mortgage Platform. It maps stage-by-stage transitions from initial borrower application through underwriting, servicing, payment processing, delinquency workflows, and portfolio analytics reporting.

---

## 2. End-to-End Business Flow Diagram

```mermaid
flowchart TD
    B[Borrower] --> MO[Mortgage Onboarding]
    MO --> UW[Underwriting]
    UW --> LA[Loan Approval]
    LA --> S[Servicing]
    S --> P[Payments]
    P --> PMD{Payment missed?}
    PMD -- No --> S
    PMD -- Yes --> D[Delinquency]
    D --> A[Analytics & Reporting]
    S --> A