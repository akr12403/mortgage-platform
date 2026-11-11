# Knowledge Base

The controlled document set that the mortgage knowledge assistant answers from (M7 Task 7.1). The assistant retrieves passages **only** from the published version in this folder, and every answer cites the document, section and chunk it came from.

## Contents (v1)

| File | `docId` | Content | Loan types | Main audience |
| --- | --- | --- | --- | --- |
| [`v1/mortgage-policy-overview.md`](v1/mortgage-policy-overview.md) | `mortgage-policy-overview` | Lifecycle, statuses, payments, ownership, roles | all | all roles |
| [`v1/underwriting-guidelines.md`](v1/underwriting-guidelines.md) | `underwriting-guidelines` | Approval criteria, loan-type rules, second review, fair lending | `CONVENTIONAL`, `FHA`, `VA` | underwriters |
| [`v1/delinquency-playbook.md`](v1/delinquency-playbook.md) | `delinquency-playbook` | 30-day rule, severity, contact timeline, escalation, cure | all | servicing agents, risk analysts |
| [`v1/servicing-faq.md`](v1/servicing-faq.md) | `servicing-faq` | Agent procedures: payments, idempotency, errors, escalation | all | servicing agents, support |
| [`v1/security-policy-excerpt.md`](v1/security-policy-excerpt.md) | `security-policy-excerpt` | Data classification, access, AI use, secrets, incidents | all | all roles |

## Source of truth

- **Platform behaviour wins.** Where a document describes what the platform does (statuses, the 30-day delinquency rule, severity bands, roles, endpoints), it must match `guides/standards.md` in the handbook and the code. The canonical places are:
  - delinquency rule and severity: `services/mortgage-service/.../service/DelinquencyService.java`;
  - roles and permissions: `docs/security/security-controls.md` and `security/Rbac.java`;
  - data classification: `docs/security/security-controls.md`.
- **Business procedure** (contact days, underwriting thresholds, escalation contacts) is defined only here, by the document owner named in each file's header.
- If a document and the code disagree, the code is treated as correct until the owner approves a fix to one or the other.

## Document format

Each file is Markdown with a YAML header that the ingestion pipeline (Task 7.2) stores as chunk metadata:

```yaml
---
docId: delinquency-playbook        # stable ID used in citations; never reused
title: Delinquency Playbook
version: v1                        # must match the folder name
loanTypes: [ALL]                   # ALL, or any of CONVENTIONAL, FHA, VA
audience: [SERVICING_AGENT, RISK_ANALYST, ADMIN]
owner: Servicing operations lead   # approves changes
classification: Internal (synthetic training policy)
lastReviewed: 2026-10-24
---
```

- `##` headings are the **sections** used in citations, so keep each one focused on one topic.
- A section that applies to one loan type only starts with a tag comment directly under its heading, for example `<!-- loanType: FHA -->`. It overrides the file-level `loanTypes` for that section, so the `loanType` filter on `/ask` can find it.
- Loan type exists only in this knowledge base for now; the platform database does not store it on the mortgage.

## Update process

1. **Never edit a published version.** Copy `v1/` to the next version folder (`v2/`) and make the changes there, updating `version` and `lastReviewed` in each changed file.
2. Keep each `docId` stable. Retire a document by removing it from the new version, never by reusing its ID for different content.
3. Open a pull request. It needs approval from the **owner** of every changed document, plus a reviewer who checks the rules against the code (see "Source of truth").
4. After merge, re-run ingestion against the new version (command documented in the service README from Task 7.2) and run the assistant's evaluation questions to confirm answers and citations.
5. Point the assistant at the new version. Keep the previous version in the repository so past answers stay traceable to the text they cited.

## No confidential client data

- Every document here is **synthetic** and classified **Internal**. The policies are simplified for training and are not real lending, servicing or regulatory guidance.
- Documents must never contain borrower names, contact details, dates of birth, balances, account numbers, uploaded documents, or any real person's data.
- Examples use synthetic business IDs only (`MTG-1002`, `BOR-001`).
- No secrets, tokens, internal hostnames or credentials, even as examples. The repository secret scan (`scripts/security-gates.sh`) runs on every pull request.
- Reviewers reject any change that adds Confidential or Restricted data (levels defined in `docs/security/security-controls.md`).
