# Final Demonstration Script (M10 Task 10.5, Session 36)

A 25-minute walk through one mortgage's life across the whole platform, followed by questions. One command drives it: `python3 scripts/final-demo.py --pause` waits for Enter before each step, runs it against the live stack and prints what to point at. Every request carries one correlation ID, so step 8 shows the whole story in Splunk with a single search. The run log (with UTC timestamps) is written to `reports/demo/<date>/`.

## Roles

| Role | Who | Does |
| --- | --- | --- |
| Presenter and driver | akr12403 | Runs the script, narrates, answers technical questions |
| Reviewer and timekeeper | Sumanth Donur | Keeps to the timings below, checks each step's pass criteria, signs off the M10 review |
| Backup driver | Reviewer | If the presenter's machine fails: opens the recorded rehearsal log and the CI run instead (fallbacks below) |

Single-person team: the presenter covers the developer, platform, security and AI roles.

## Before the session (15 minutes earlier)

```bash
cd ~/projects/mortgage-platform
git switch develop && git pull
bash scripts/splunk/local-up.sh                          # stack + Splunk + log shipping; all healthy
curl -s localhost:8001/health/ready                      # "status":"UP" (LLM key + knowledge base)
cd tests/e2e && npm test && cd ../..                     # 16/16: the platform is good before going live
python3 scripts/final-demo.py                            # one dry run; must end "20 checks, all checks passed"
```

**Optional: start from the seed data.** E2E, performance and drill runs leave their own borrowers and mortgages in the local database (in the rehearsal the portfolio showed 28 mortgages, 11 of them delinquent), which makes the portfolio figures in step 5 harder to explain. To present on the clean seed data, reset the day before (the knowledge base must be ingested again, which makes embedding calls):

```bash
docker compose down -v && docker compose up -d     # empty volume -> schema + seed; seed users recreated from .env
docker compose run --rm knowledge-ingest
bash scripts/splunk/local-up.sh
```

Browser tabs, in this order:
1. The README (architecture section) on GitHub.
2. Splunk dashboard *Mortgage Platform: Service Health*: http://localhost:8002/en-US/app/search/mortgage_platform_overview, *Last 15 minutes*.
3. Splunk search (empty), for step 8.
4. Splunk *Activity → Triggered Alerts*.
5. GitHub Actions: the latest green `ci` run on `develop`, with `e2e-tests` expanded.
6. [rca-2026-11-10.md](rca-2026-11-10.md) and [production-readiness.md](production-readiness.md).

Terminal: font large, window wide (the Splunk table in step 8 is about 110 columns).

## The script

| # | Time | Show | Say | Pass criteria |
| --- | --- | --- | --- | --- |
| 0 | 2 min | README architecture; terminal header with the 4 health checks | Four services: mortgage (Java), servicing (Java), analytics (Python), knowledge assistant (Python RAG). PostgreSQL is the system of record; lifecycle events go through SNS → SQS to the consumers. Everything runs in containers, built and scanned by one pipeline. Today we follow one mortgage from application to delinquency, then look at it the way operations would. | All 4 services UP |
| 1 | 3 min | **Onboarding** | An underwriter registers a new borrower and a mortgage with a PENDING loan. Business IDs (`BOR-…`, `MTG-…`) only; internal IDs never drive anything. Creating the mortgage publishes `MortgageCreated`. | Borrower 201; mortgage 201, PENDING |
| 2 | 2 min | **Underwriting decision** | The approval workflow: only ADMIN or UNDERWRITER can decide, and the approver's role is taken from the signed token, not from the request (an M6 finding we fixed). Approval moves the mortgage to ACTIVE and publishes `LoanApproved`. servicing-service already shows both events: that's the asynchronous path working. | ACTIVE; history has MORTGAGE_CREATED and LOAN_APPROVED |
| 3 | 3 min | **Payment** | A servicing agent posts the first installment with an `Idempotency-Key`. The client retries the same request, as a client would after a timeout: the API replays the stored result instead of charging twice. The balance drops once; the servicing history has exactly one `PAYMENT_POSTED`. | 200; replay header true; balance 318,150.00; one PAYMENT_POSTED |
| 4 | 3 min | **Delinquency** | An earlier installment, due 45 days ago, failed. Thirty or more days past due on an ACTIVE loan makes it DELINQUENT; `PaymentMissed` and `LoanDelinquent` go out, and servicing builds the delinquency snapshot: 45 days, MODERATE (30–59). The same rule runs as a daily batch at 02:00 UTC. | DELINQUENT; snapshot MODERATE; PAYMENT_MISSED and DELINQUENCY_ASSIGNED in the history |
| 5 | 3 min | **Analytics** (terminal), then the **Splunk dashboard** (tab 2) | The risk analyst's view: portfolio counts and delinquency rate, the delinquent list (our mortgage is in it), and the borrower's risk summary. ADMIN sees the borrower's name; the risk analyst gets the same figures without it, because names aren't needed for that job (data minimization, M6). On the dashboard: payment success rate and p95 against the SLO, request rate, errors. | Summary 200; mortgage in the delinquent list; no name for RISK_ANALYST |
| 6 | 2 min | **Security** | Support tries to approve a loan: 403 `ACCESS_DENIED`. No token: 401. Support reading borrower PII: 403. Deny by default, one role matrix enforced in every service and tested in CI on every change (J4, the RBAC smoke test). | 403, 401, 403 |
| 7 | 3 min | **Knowledge assistant** | A policy question gets an answer built only from the approved knowledge base, with citations to the exact sections; citations are checked in code against what was retrieved. Asking it to act on our delinquent loan flags `requiresHumanApproval`: the assistant advises, a person decides. An off-topic question gets "insufficient context", not an invented answer. | Answer with ≥ 1 citation; approval flag true; off-topic: no citations |
| 8 | 3 min | **Splunk correlation** (terminal table, then tab 3 with the printed search) | Every request in this demo carried one correlation ID. One search shows the whole story: each service's request lines with the route template, status and duration, and the consumer lines in servicing and analytics that came from the events, because the ID travels inside every event. This is how support goes from a user's error message to the cause. | Lines from ≥ 3 services; consumer lines present |
| 9 | 3 min | **Operations**: Triggered Alerts (tab 4), the RCA (tab 6), the CI run (tab 5), the readiness verdict | We stopped the database under load on purpose. First drill: the alert came after 1 min 4 s and requests hung for 30 s. We fixed it (fail fast with 503, a database alert, better routing in the logs) and re-ran it: alert in 40 s, failures in 3 s. The runbook has a section per alert. Every change runs build, unit tests, secret/SAST/dependency scans, container scans, integration and these five E2E journeys before anything is published. Readiness: GO with conditions; the conditions are what stands between this and real borrower data. | Alerts listed; CI run green including `e2e-tests` |
| | 5 min | **Questions** | | |

**Total:** 24 minutes of demo plus 5 of questions.

## Likely questions

| Question | Short answer | Where |
| --- | --- | --- |
| What if the database goes down? | 503 with `Retry-After` within 3 s; alert within a minute; services reconnect by themselves; payments are idempotent so retries are safe | [RCA](rca-2026-11-10.md) |
| Why is nothing running in AWS? | The sandbox has no database (ECS at 0 tasks); the infrastructure, images, data platform and deployments are real. A managed database is go-live condition C-2 | [readiness](production-readiness.md#appendix-go-live-recommendation) |
| How do you deploy and roll back? | `deploy-dev.sh <tag>`: tested images only, Terraform plan then apply; rollback is the same command with the previous tag (drilled 2026-11-09) | [runbook](runbook.md#rollback) |
| How do you stop the AI from making things up? | Similarity gate before the model is called, context-only prompt, citations verified against retrieved passages, human approval for case actions, PII redacted before any call | [docs/ai](../ai/) |
| What's not production-ready? | Six conditions: Spring Boot 4, managed database with backups, MFA and token revocation, CI deploys via OIDC, performance test in the target environment, shared Splunk with on-call | [known issues](known-issues.md) |
| How is it tested? | Unit and API tests per service, contract tests, security and integration tests on the real images, and five E2E journeys as a pipeline gate | [test strategy](test-strategy.md) |

## Fallbacks

| If | Then |
| --- | --- |
| A step prints FAIL | Say what it checks, open the matching scenario in the last green `e2e-tests` run (tab 5), and continue with the next step; the script doesn't stop |
| The assistant isn't ready (no key or no knowledge base) | Skip to step 8; show J5 in the CI run, where it runs against the stub |
| Splunk is slow to show the lines | Wait 30 s and press Enter again on the search in tab 3; or show the rehearsal's run log, which has the same table |
| The laptop or Docker fails | Present from the recorded rehearsal log below, the dashboard screenshots in the RCA, and the CI run |

## Rehearsal log

Rehearsals use `python3 scripts/final-demo.py --pause` with the timings above. The script's run log is in `reports/demo/<date>/` (git-ignored); the table below is the record.

| Date (UTC) | Run | Duration | Checks | Notes |
| --- | --- | --- | --- | --- |
| 2026-11-11 01:02:57–01:03:25 | Technical dry run, `--pause` stepped through without narration | 28 s of API time | **20/20 passed** | correlationId `final-demo-c855d315d881`, BOR-578, MTG-7620. Step 8: 61 log lines from all 4 services, servicing consumer lines for all 5 events. Step 9: all 5 alerts listed. Assistant answer with 2 citations (confidence 0.65), off-topic 0.03. Portfolio figures include test data (see *Optional* above) |
| | Timed rehearsal with narration (target 24 min + questions) | | | |

## Sign-off

- [x] Technical dry run: 20/20 checks passed, 2026-11-11 (record above)
- [ ] Timed rehearsal with narration within 30 minutes (record above)
- [ ] Final demonstration given; reviewer: Sumanth Donur
