---
docId: security-policy-excerpt
title: Information Security Policy (Excerpt)
version: v1
loanTypes: [ALL]
audience: [ALL_ROLES]
owner: Security lead
classification: Internal (synthetic training policy)
lastReviewed: 2026-10-24
---

# Information Security Policy (Excerpt)

> Synthetic excerpt written for the capstone platform, summarising `docs/security/security-controls.md`. It is not a real company policy.

This excerpt covers the security rules every platform user must follow: how data is classified, who may see what, how to use AI tools, how secrets are handled, and how to report an incident.

## Data classification

Every piece of data has one of four levels. A record takes the highest level of any field in it.

| Level | Meaning | Examples |
| --- | --- | --- |
| **Public** | Safe for anyone | health-check responses, published product information |
| **Internal** | For staff and systems; low harm if leaked | business IDs (`BOR-###`, `MTG-####`), statuses, aggregate figures, API specifications, these policy documents |
| **Confidential** | Personal or financial information about an identifiable borrower | names, email, phone, loan terms, balances, payments, delinquency details |
| **Restricted** | Severe harm if leaked | date of birth, uploaded documents (pay stubs, W-2s, tax returns), passwords, tokens, signing keys, database and cloud credentials |

A business ID on its own is Internal. Joined to a name and a balance, it becomes Confidential.

## Handling rules by level

- **Internal:** sign-in required; may appear in logs, events and tickets.
- **Confidential:** only roles that need it for their job; encrypted in transit and at rest; **never** in logs, events, URLs or AI prompts; masked outside production.
- **Restricted:** everything for Confidential, plus the smallest possible set of people and systems, encrypted storage with audited key use, never exported to analytics or non-production, and rotated immediately if exposure is suspected.

## Access control

- Every user has a named account. Shared accounts are not allowed.
- Access is granted by role: `ADMIN`, `UNDERWRITER`, `SERVICING_AGENT`, `RISK_ANALYST`, `SUPPORT`.
- Only `ADMIN`, `UNDERWRITER` and `SERVICING_AGENT` can read borrower personal details.
- Only `ADMIN` and `UNDERWRITER` can approve or decline loans.
- Only `ADMIN` and `SERVICING_AGENT` can post payments and run delinquency evaluation.
- The platform denies any action not explicitly allowed for a role (deny by default).
- Sign-in attempts are rate limited: 10 per minute per account and 60 per minute per network address.

## Use of AI tools

- Only approved AI tools may be used with platform information. The mortgage knowledge assistant is approved for **Internal** policy questions.
- **Never** put Confidential or Restricted data into any AI prompt: no borrower names, contact details, dates of birth, balances, account numbers, documents or credentials.
- Refer to a loan only by its business ID, and only when needed.
- AI answers are advisory. Underwriting decisions, delinquency escalations, fee waivers and status changes are always made by a person.
- If an AI answer has no citation, or says it does not have enough context, do not act on it; check the source policy or ask the policy owner.
- Report any AI answer that contains personal data or invents a policy to the security lead.

## Secrets

- Passwords, tokens, API keys and signing keys live only in environment variables or a secrets manager, never in source code, tickets, chat or documents.
- Never commit a `.env` file. Automated secret scanning blocks merges that contain secrets.
- Rotate a secret immediately if it may have been exposed, following the secrets-rotation runbook (`docs/operations/runbook.md`).
- API keys for AI services are scoped to the minimum endpoints and models, have a spending limit, and expire.

## Logging

- Logs carry a correlation ID for every request so one request can be traced across services.
- Logs may contain business IDs, statuses and error codes.
- Logs must not contain borrower personal data, passwords, tokens, full request bodies with personal data, or AI prompts that have not had personal data removed.

## Incident reporting

Report immediately to the administrator and the security lead if you:

- see borrower personal data somewhere it should not be (a log, ticket, chat, AI prompt or email);
- suspect an account, password, token or API key has been exposed;
- notice access you should not have, or a colleague using someone else's account;
- receive a suspicious request for borrower information.

Do not try to investigate or delete evidence yourself. The security lead records the incident, contains it, rotates any affected secrets and decides whether borrowers or regulators must be notified.
