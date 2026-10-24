---
docId: mortgage-policy-overview
title: Mortgage Servicing Policy Overview
version: v1
loanTypes: [ALL]
audience: [ALL_ROLES]
owner: Mortgage operations lead
classification: Internal (synthetic training policy)
lastReviewed: 2026-10-24
---

# Mortgage Servicing Policy Overview

> Synthetic policy written for the capstone platform. It is not real lending or servicing guidance.

This document summarises how a mortgage moves through the platform, from application to payoff, and which team owns each stage. Detailed rules live in the underwriting guidelines, the delinquency playbook, the servicing FAQ and the security policy excerpt.

## Scope

- The platform services residential first-lien mortgages for three loan types: **`CONVENTIONAL`**, **`FHA`** and **`VA`**.
- Loan type is used by underwriting and by the knowledge assistant's filters. It is not yet stored on the mortgage record.
- All data in the platform's non-production environments is synthetic. No real borrower data may be loaded into development, test or demo environments.

## Mortgage lifecycle

| Status | Meaning | How it is reached |
| --- | --- | --- |
| `PENDING` | Application created; waiting for an underwriting decision | Mortgage created by an underwriter or administrator |
| `ACTIVE` | Loan approved and being serviced | Underwriting decision `APPROVED` |
| `DELINQUENT` | 30 or more calendar days past due on the oldest unpaid installment | Daily or on-demand delinquency evaluation |
| `CLOSED` | No longer serviced | Underwriting decision `DECLINED` (application closed). Closing a paid-off loan is not yet automated. |

`FORECLOSURE` is a reserved status. It is not used by the capstone platform.

## Underwriting decisions

- Every new mortgage starts with underwriting decision `PENDING`.
- Only an **underwriter** or **administrator** can record a decision of `APPROVED` or `DECLINED`.
- `APPROVED` moves the mortgage to `ACTIVE` and publishes a `LoanApproved` event.
- `DECLINED` moves the mortgage to `CLOSED`.
- A decision is final in the platform: a second decision on the same loan is rejected with `409 UNDERWRITING_ALREADY_DECIDED`. Reversing a decision needs an administrator and a written reason, and is done outside the platform.

## Payments

- Each billing period has a due date. Payments are recorded with one of four statuses: `SCHEDULED`, `POSTED`, `FAILED`, `REVERSED`.
- Only `POSTED` payments count toward the due date.
- Payments are posted by a **servicing agent** or **administrator** through `POST /api/v1/mortgages/{id}/payments`.
- Servicing policy requires an **`Idempotency-Key`** header (1–255 characters) on every payment request. The platform accepts payments without one, but then a retried request can create a duplicate payment. Retrying with the same key and the same body never creates a second payment.
- Posting a payment publishes a `PaymentReceived` event, which servicing-service records in the servicing history.

## Delinquency

A mortgage becomes `DELINQUENT` when no payment has posted 30 calendar days after a due date. Severity is `MODERATE` (30–59 days), `SEVERE` (60–89) or `CRITICAL` (90+). The full rule, contact timeline and escalation steps are in the delinquency playbook.

## Servicing history

- servicing-service keeps a time-ordered history for every mortgage: approvals, payments, missed payments, delinquency changes and agent notes.
- Agents add notes with `POST /api/v1/mortgages/{id}/servicing-events`.
- Any role can read the history with `GET /api/v1/mortgages/{id}/servicing-history`.

## Ownership

| Area | Owning service | Owning team |
| --- | --- | --- |
| Borrowers, mortgages, loans, payments, mortgage status | mortgage-service | Origination and servicing |
| Servicing history, delinquency snapshot | servicing-service | Servicing operations |
| Portfolio and delinquency analytics, document uploads | mortgage-analytics-service | Risk analytics |
| Policy knowledge base and assistant | mortgage-knowledge-assistant | Platform AI team |

## Roles

| Role | What the role does |
| --- | --- |
| `ADMIN` | Full access; user provisioning; status corrections |
| `UNDERWRITER` | Creates borrowers and mortgages; approves or declines loans |
| `SERVICING_AGENT` | Posts payments; runs delinquency evaluation; contacts borrowers; adds servicing notes |
| `RISK_ANALYST` | Reads portfolio and delinquency analytics |
| `SUPPORT` | Read-only troubleshooting |

## Policy changes

- Policy documents are versioned in the knowledge base (`knowledge/v1/`, `v2/`, ...).
- A policy change needs approval from the document owner and a pull request review before it is published.
- The knowledge assistant answers only from the published version it was built from.
