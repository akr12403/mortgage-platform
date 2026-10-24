---
docId: underwriting-guidelines
title: Underwriting Guidelines
version: v1
loanTypes: [CONVENTIONAL, FHA, VA]
audience: [UNDERWRITER, ADMIN]
owner: Chief underwriter
classification: Internal (synthetic training policy)
lastReviewed: 2026-10-24
---

# Underwriting Guidelines

> Synthetic policy written for the capstone platform. The thresholds are simplified for training and are not real agency, investor or regulatory guidance.

These guidelines tell an underwriter when an application can be approved, when it must be declined, and when it needs a second review. The underwriter always makes the decision. The knowledge assistant may summarise an application against these guidelines, but it never approves or declines a loan.

## Decision process

1. The application is created with underwriting decision `PENDING`.
2. The underwriter checks the application against the general criteria and the criteria for its loan type.
3. The underwriter records `APPROVED` or `DECLINED` with `POST /api/v1/mortgages/{id}/underwriting-decision`.
4. Only `UNDERWRITER` and `ADMIN` can record a decision. A decision cannot be changed in the platform once recorded.
5. Every decision must have a written rationale in the loan file that names the criteria checked.

## General criteria

These apply to every loan type unless the loan-type section says otherwise.

| Measure | How it is calculated | Approve up to | Second review | Decline |
| --- | --- | --- | --- | --- |
| Debt-to-income ratio (DTI) | Monthly debt payments, including the new mortgage, divided by gross monthly income | 43% | 43.01–50% | over 50% |
| Loan-to-value ratio (LTV) | Loan amount divided by the lower of appraised value and purchase price | loan-type limit | — | over the loan-type limit |
| Credit score | Middle of three bureau scores | loan-type minimum | 20 points below minimum | more than 20 points below minimum |
| Employment history | Continuous income history | 2 years | 1–2 years with explanation | under 1 year without explanation |
| Cash reserves | Months of mortgage payments in liquid assets after closing | 2 months | 1 month | none |

## Conventional loans
<!-- loanType: CONVENTIONAL -->

- Minimum credit score: **620**.
- Maximum LTV: **95%**.
- When LTV is above **80%**, private mortgage insurance (PMI) is required until LTV falls to 78%.
- Minimum down payment: 5% of the purchase price.
- Maximum term: 360 months.

## FHA loans
<!-- loanType: FHA -->

- Minimum credit score: **580** with 3.5% down payment.
- Credit scores from 500 to 579 need a 10% down payment and a second review.
- Maximum LTV: **96.5%**.
- Mortgage insurance premium (MIP) is required on every FHA loan, whatever the LTV.
- The property must be the borrower's primary residence.

## VA loans
<!-- loanType: VA -->

- Available only to eligible service members and veterans with a certificate of eligibility in the loan file.
- Minimum credit score: **620**.
- Maximum LTV: **100%**; no down payment is required.
- No monthly mortgage insurance; a one-time funding fee applies unless the borrower is exempt.
- Residual income must meet the VA regional table, in addition to the DTI check.

## Second review

A second underwriter or an administrator must review the application before a decision when any of these is true:

- DTI is between 43.01% and 50%;
- the credit score is up to 20 points below the loan-type minimum;
- the borrower has less than 2 years of continuous income;
- the application has any exception to these guidelines;
- the underwriter has a personal or business relationship with the borrower.

The second reviewer records their name and agreement in the loan file. The decision is then recorded by the first underwriter.

## Automatic decline reasons

An application must be declined when:

- DTI is over 50%;
- LTV is over the loan-type limit;
- the credit score is more than 20 points below the loan-type minimum;
- required documents (income, identity, appraisal) are missing after two requests;
- there is evidence of misrepresentation or fraud. Report suspected fraud to the administrator; do not discuss it with the borrower.

## Fair lending

- Decisions must be based only on the criteria in these guidelines.
- Never consider race, colour, religion, national origin, sex, marital status, age (beyond capacity to contract), disability, familial status or receipt of public assistance.
- The same criteria apply to every applicant for the same loan type.
- An AI-generated summary is advisory only. It must not be the reason for a decision, and it must not be stored as the decision rationale.

## Required documents

| Document | Purpose | Retention |
| --- | --- | --- |
| Two recent pay stubs | Current income | Life of loan plus 7 years |
| Two years of W-2s or tax returns | Income history | Life of loan plus 7 years |
| Two months of bank statements | Reserves and down payment source | Life of loan plus 7 years |
| Government-issued photo ID | Identity verification | Life of loan plus 7 years |
| Appraisal report | Property value for LTV | Life of loan plus 7 years |

Documents are uploaded with `POST /api/v1/documents/upload` (roles `ADMIN`, `UNDERWRITER`, `SERVICING_AGENT`; PDF, PNG, JPEG or plain text; at most 10 MB). Uploaded documents are classified **Restricted**.
