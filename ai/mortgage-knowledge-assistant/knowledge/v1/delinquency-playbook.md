---
docId: delinquency-playbook
title: Delinquency Playbook
version: v1
loanTypes: [ALL]
audience: [SERVICING_AGENT, RISK_ANALYST, ADMIN]
owner: Servicing operations lead
classification: Internal (synthetic training policy)
lastReviewed: 2026-10-24
---

# Delinquency Playbook

> Synthetic policy written for the capstone platform. It is not real lending or servicing guidance.

This playbook explains when a mortgage becomes delinquent, how severity is assigned, who contacts the borrower and when, and which steps always need a person to decide. The rules in the "Definition" and "Severity" sections are the same rules the platform code enforces (`DelinquencyService` in mortgage-service, canonical rule in `guides/standards.md`).

## Definition

- Every billing period has a **due date** (`payment.due_date`).
- A payment counts only when its status is **`POSTED`**. `SCHEDULED`, `FAILED` and `REVERSED` payments do not satisfy the due date.
- **Days past due** is the number of calendar days between the oldest unpaid due date and today (UTC).
- When a mortgage is **30 or more calendar days past due** and its status is `ACTIVE`, its status changes to **`DELINQUENT`**.
- The **delinquent-since date** is the due date plus 30 days. For example, a payment due on 1 March that is still unpaid becomes delinquent on 31 March.
- Only `ACTIVE` mortgages can become `DELINQUENT`. `PENDING` and `CLOSED` mortgages are never evaluated.
- There is no grace period on the 30-day threshold: day 30 is delinquent, day 29 is not.

## Severity

Severity is set when the `DELINQUENT` status is assigned, from the days past due at that moment.

| Days past due | Severity | Meaning |
| --- | --- | --- |
| 30–59 | `MODERATE` | One payment missed; early-stage collection |
| 60–89 | `SEVERE` | Two payments missed; loss-mitigation review required |
| 90 or more | `CRITICAL` | Three or more payments missed; default-management review required |

Severity is recorded in the servicing-service delinquency snapshot and shown by `GET /api/v1/mortgages/{id}/delinquency`.

## How the platform detects delinquency

1. **Daily evaluation.** A scheduled job in mortgage-service evaluates the whole portfolio every day at **02:00 UTC**.
2. **On-demand evaluation.** A servicing agent or administrator can run the same evaluation with `POST /api/v1/delinquency-evaluations` (roles `SERVICING_AGENT` or `ADMIN`). It is used for demos and after bulk payment corrections.
3. **Failed or reversed payment.** When a payment attempt for a past due date fails or is reversed, the mortgage is evaluated straight away.

Two events are published:

- **`PaymentMissed`**: a due date has passed with no posted payment. It carries the mortgage ID, the due date and the days past due.
- **`LoanDelinquent`**: the mortgage was marked `DELINQUENT`. It carries the delinquent-since date, days past due and severity.

servicing-service consumes `LoanDelinquent`, stores the delinquency snapshot and adds a servicing-history entry. The analytics service counts the loan in the delinquency rate: `DELINQUENT` mortgages divided by `ACTIVE` plus `DELINQUENT` mortgages.

## Timeline

The contact timeline starts at the missed due date (day 0). Automated steps are done by the platform; every other step is done by a servicing agent and recorded as a servicing event.

| Day | Step | Who | Automated? |
| --- | --- | --- | --- |
| 1 | Payment not posted; `PaymentMissed` published on the next evaluation | Platform | Yes |
| 5 | Courtesy reminder (email or letter) | Servicing agent | No |
| 15 | First phone attempt; confirm the borrower knows the amount due | Servicing agent | No |
| 30 | Mortgage marked `DELINQUENT`, severity `MODERATE`; `LoanDelinquent` published | Platform | Yes |
| 30–32 | Second phone attempt within **2 business days** of delinquency; send written delinquency notice | Servicing agent | No |
| 45 | Follow-up call; offer a repayment plan if the borrower asks | Servicing agent | No |
| 60 | Severity reaches `SEVERE`; refer to loss-mitigation review | Servicing agent, then underwriter | No |
| 90 | Severity reaches `CRITICAL`; default-management review by an administrator | Administrator | No |

Every contact attempt, successful or not, must be recorded with `POST /api/v1/mortgages/{id}/servicing-events` so the servicing history shows the full timeline.

## Severity updates after day 30

The platform assigns severity once, when the mortgage first becomes `DELINQUENT`. A later evaluation does not raise `MODERATE` to `SEVERE` automatically in the current version, because only `ACTIVE` mortgages are evaluated. Agents must check days past due at the day-60 and day-90 milestones and escalate by hand. Automatic severity refresh is a known backlog item.

## Cure and reinstatement

- A delinquency is **cured** when every past-due installment has a `POSTED` payment.
- The current platform version does **not** return a cured mortgage to `ACTIVE` automatically.
- The servicing agent records the cure as a servicing event ("Delinquency cured: all past-due installments posted") and raises a status-correction request to an administrator.
- A partial payment does not cure a delinquency. It is posted, but the oldest unpaid due date still drives days past due.

## Repayment plans and forbearance

- A **repayment plan** spreads the past-due amount over up to 6 future payments. A servicing agent may offer it for `MODERATE` delinquencies.
- **Forbearance** (temporary payment reduction or pause) is offered only after a documented hardship review by an underwriter.
- Plans and forbearance are recorded as servicing events. The platform does not yet model them as data.

## Decisions that always need a person

The knowledge assistant may explain these steps, but it must never recommend them as a final decision:

- referring a loan to foreclosure or any legal action;
- approving forbearance, a loan modification or a repayment plan longer than 6 months;
- waiving fees or changing the amount owed;
- correcting a mortgage status by hand.

Foreclosure is outside the capstone platform's scope (`FORECLOSURE` status is not used).

## Borrower communication rules

- Use only the email address and phone number on the borrower record (`GET /api/v1/borrowers/{id}`, roles `ADMIN`, `UNDERWRITER`, `SERVICING_AGENT`).
- Never discuss the loan with anyone other than the borrower or an authorised third party on file.
- Never leave loan details in a voicemail; ask for a call back.
- Do not copy borrower names, contact details or balances into tickets, chat tools or AI prompts. Refer to the loan by its business ID, for example `MTG-1002`.
