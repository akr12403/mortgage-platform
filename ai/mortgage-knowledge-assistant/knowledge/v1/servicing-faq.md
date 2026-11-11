---
docId: servicing-faq
title: Servicing Agent FAQ
version: v1
loanTypes: [ALL]
audience: [SERVICING_AGENT, SUPPORT, ADMIN]
owner: Servicing operations lead
classification: Internal (synthetic training policy)
lastReviewed: 2026-10-24
---

# Servicing Agent FAQ

> Synthetic procedures written for the capstone platform. They are not real servicing guidance.

Answers to the questions servicing agents ask most often. Each answer names the platform endpoint and the roles allowed to use it.

## How do I post a borrower's payment?

1. Find the mortgage by its business ID (for example `MTG-1002`) with `GET /api/v1/mortgages/{id}`.
2. Post the payment with `POST /api/v1/mortgages/{id}/payments`, giving the due date, paid date, amount and status `POSTED`.
3. Send an `Idempotency-Key` header with every payment. The platform treats it as optional, but servicing policy requires it. Use a fresh key for each new payment and the **same** key when retrying the same payment.
4. Add a servicing note with `eventType` in UPPER_SNAKE_CASE (for example `PAYMENT_NOTE`) if anything about the payment is unusual.
5. Check the payment appears in `GET /api/v1/mortgages/{id}/payments` and in the servicing history.

Allowed roles: `SERVICING_AGENT`, `ADMIN`.

## What happens if I submit the same payment twice?

- **Same `Idempotency-Key`, same body:** the platform stores the payment once and returns the original payment for the retry.
- **Same key, different body:** the platform rejects the request with `409 IDEMPOTENCY_KEY_REUSED`. Use a new key for a different payment.
- **Different key, or no key:** the platform creates a second payment. Before retrying after a timeout, always reuse the original key.

## What do I do when a payment fails or is reversed?

1. Record the payment with status `FAILED` (payment did not go through) or `REVERSED` (payment was returned after posting, for example insufficient funds).
2. The platform checks the mortgage straight away. If the due date has passed with no posted payment, it publishes `PaymentMissed`, and if the mortgage is 30 or more days past due it marks it `DELINQUENT`.
3. Contact the borrower following the delinquency playbook timeline.
4. Add a servicing note explaining the failure reason.

## How do I check whether a loan is delinquent?

- `GET /api/v1/mortgages/{id}` shows the mortgage status (`ACTIVE`, `DELINQUENT`, ...).
- `GET /api/v1/mortgages/{id}/delinquency` (servicing-service) shows the delinquent-since date, days past due and severity.
- Both are readable by every role.

## When should I run a delinquency evaluation by hand?

The platform evaluates the whole portfolio every day at 02:00 UTC. Run `POST /api/v1/delinquency-evaluations` by hand only:

- after posting or correcting a batch of back-dated payments;
- during a demo or training session;
- when an administrator asks you to.

Allowed roles: `SERVICING_AGENT`, `ADMIN`.

## How do I add a note to a loan?

Use `POST /api/v1/mortgages/{id}/servicing-events` with an `eventType` in UPPER_SNAKE_CASE (for example `BORROWER_CONTACT`) and a `description` of at most 2,000 characters. Write notes as facts ("Borrower called; promised payment by 15 March"). Never include card numbers, bank account numbers, passwords or the borrower's date of birth in a note.

Allowed roles: `SERVICING_AGENT`, `ADMIN`.

## Why do I get a 403 error?

`403 ACCESS_DENIED` means you are signed in but your role is not allowed to do that action. For example, a `SUPPORT` user cannot post payments and a `SERVICING_AGENT` cannot approve loans. Ask an administrator if you need a different role; do not share accounts.

## Why do I get a 401 error?

`401` means your sign-in token is missing, invalid or expired. Sign in again with `POST /api/v1/auth/login`. Tokens expire after a fixed time, so long-running sessions must sign in again.

## Why do I get a 429 error?

`429 RATE_LIMITED` means too many requests in a short time, for example more than 60 write requests per minute or more than 10 sign-in attempts per minute for one account. Wait for the number of seconds in the `Retry-After` header, then try again.

## Can I see a borrower's personal details?

`SERVICING_AGENT`, `UNDERWRITER` and `ADMIN` can read borrower name, email, phone and date of birth with `GET /api/v1/borrowers/{id}`. `RISK_ANALYST` and `SUPPORT` cannot. Look up personal details only when you need them for the task in front of you.

## Can I paste loan details into the knowledge assistant?

No borrower names, contact details, dates of birth, balances or account numbers may be pasted into the assistant or any other AI tool. Ask the question in general terms ("What happens at 60 days past due?") or refer to the loan only by its business ID.

## Who do I escalate to?

| Situation | Escalate to |
| --- | --- |
| Loan reaches 60 days past due (`SEVERE`) | Underwriter, for loss-mitigation review |
| Loan reaches 90 days past due (`CRITICAL`) | Administrator, for default-management review |
| Borrower requests forbearance or a loan modification | Underwriter |
| Mortgage status looks wrong | Administrator |
| Suspected fraud or a data leak | Administrator, immediately |
