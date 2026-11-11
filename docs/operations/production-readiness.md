# Production Readiness Review (M10 Task 10.4)

| | |
| --- | --- |
| **Release candidate** | `develop` after PR #117 (`3fab39d`) plus this PR. To be tagged `v1.0.0-capstone-rc1`, then `v1.0.0-capstone` |
| **Review date** | 2026-11-10/11 (UTC); dry run below |
| **Prepared by** | akr12403 (single-person team: developer, platform, security and AI lead roles) |
| **Reviewer** | Sumanth Donur |
| **Recommendation** | **GO with conditions**: release `v1.0.0-capstone` (synthetic data, dev environment). Not for real borrower data until conditions C-1 to C-6 are met ([appendix](#appendix-go-live-recommendation)) |

## Readiness checklist

| # | Item | Status | Evidence |
| --- | --- | --- | --- |
| 1 | **Functional validation** | ✅ | E2E J1–J5: 16/16 scenarios locally (real LLM, 2026-11-10) and in CI run [42927278133](https://github.com/akr12403/mortgage-platform/actions/runs/42927278133) (`e2e-tests`, 16/16, 115 steps). Unit suites (Java 105, analytics 80, assistant 119, TS 16), contract, integration green on every merge. [Test strategy](test-strategy.md) |
| 2 | **Security validation** | ✅ | [Re-scan](#vulnerability-re-scan) 2026-11-11: secrets, SAST, SCA all pass, 0 findings. Every Critical and High finding from M6 closed with a regression test ([closure](#m6-findings-closure)). One accepted exception (VULN-M6-019), expiring 2026-12-31. J4 and the RBAC smoke prove 401/403 on the running stack |
| 3 | **Performance validation (smoke)** | ✅ | [Perf smoke](#performance-smoke) 2026-11-11: 124,774 requests in 2 min, 0 errors; payment p95 209 ms (target < 500 ms), portfolio summary p95 11 ms (target < 2 s), event lag ~115 ms (target < 60 s) |
| 4 | **CI/CD validation** | ✅ | `ci` green on every merge PR #108–#117: build → unit → secrets/SAST/SCA → container build → container scan → integration + E2E → publish. [cicd.md](cicd.md) |
| 5 | **Infrastructure validation** | ✅ | `tf.sh dev plan -detailed-exitcode` on 2026-11-11: no changes (dev matches the code). test and prod plan 90 to add from the same modules. [Drift exercise](terraform-drift-exercise.md), [terraform.md](terraform.md) |
| 6 | **Monitoring validation** | ✅ | Splunk (local): JSON logs with `correlationId` from all 4 services, dashboard, 5 alerts with runbook sections, SLOs. In the drill re-run, 4 alerts fired 40 s after the failure, the 5th at 1 min 40 s ([RCA §7](rca-2026-11-10.md#7-re-run-after-the-fixes-p-5)) |
| 7 | **Backup / recovery considerations** | ✅ local, ⚠ AWS (C-2) | Local: [backup/restore check](#backup-and-recovery) 2026-11-11, all 11 tables restored with identical row counts. Terraform state: versioned bucket, 30-day history. AWS has no database yet (ECS placeholder), so RDS backups are a go-live condition |
| 8 | **Rollback procedure tested** | ✅ | Dev rollback drill 2026-11-09: rolled back to the previous release with one command (`deploy-dev.sh sha-fe79157`, task definition `:3 → :4`), then forward again ([deployment record](cicd.md#deployment-record)). ECS circuit breaker on all services. Database restore tested locally (item 7). [Runbook: Rollback](runbook.md#rollback) |
| 9 | **Runbook complete** | ✅ | [runbook.md](runbook.md): secrets rotation, startup/deploy/rollback, 5 alerts, common failures (new). Plus [incident-response.md](incident-response.md), [messaging-runbook.md](messaging-runbook.md), [data-pipeline-runbook.md](data-pipeline-runbook.md), [KT checklist](kt-checklist.md) |
| 10 | **Known issues documented** | ✅ | [known-issues.md](known-issues.md): 18 platform issues with impact, workaround and tracking item, plus 4 developer-machine notes |
| 11 | **Risk register updated** | ✅ | [risk-register.md](../security/risk-register.md) reviewed 2026-11-11: residual risks unchanged; the R-04 and R-05 acceptances, which ran to M9 sign-off, renewed to go-live with the same conditions |
| 12 | **Go-live recommendation signed by team** | ⏳ | [Appendix](#appendix-go-live-recommendation). Signed by the team; reviewer sign-off pending (box below) |

## Dry run (Session 35 lab)

A release rehearsal on 2026-11-10/11, running every check above against `develop` as it will be tagged. Times are UTC.

| Time | Step | Result |
| --- | --- | --- |
| 11-10 23:46 | E2E J1–J5 against the local stack (real LLM), Cucumber 11 | 16/16 passed. `npm` flagged deprecated `glob`/`uuid` and 7 moderate advisories |
| 11-10 23:50 | Upgraded to Cucumber 13.3.0 and playwright-core 1.65.0, re-ran | 16/16 passed; `npm audit`: 0 vulnerabilities |
| 11-11 00:01 | CI `e2e-tests` on the scanned images, J5 with the LLM stub (run 42927278133) | 16/16 passed; job 2 min 35 s |
| 11-11 00:14 | Backup and restore check | 11/11 tables match |
| 11-11 00:15 | Performance smoke, 2 min | 0 errors; all targets met |
| 11-11 00:18 | Security gates (`security-gates.sh all`) | all pass |
| 11-11 ~00:22 | Terraform plan for dev | no changes |

**Found during the dry run, and fixed:**
- The SCA gate didn't scan the new E2E suite's lockfile. It now scans `tests/e2e` like the TS client (PR #117).
- The first E2E dependency set (Cucumber 11) pulled deprecated packages with moderate advisories. Upgraded before merging.
- Node.js wasn't installed on the developer machine; the CI runners bring their own. Added to the prerequisites in [tests/e2e/README.md](../../tests/e2e/README.md) and the [KT checklist](kt-checklist.md).
- The developer's `gh` cache had wrong file ownership, which stopped `gh run view --log`. Local only; workaround in [known issues](known-issues.md).

## Vulnerability re-scan

`sh scripts/security-gates.sh all` on `develop` (147 commits), 2026-11-11 00:18 UTC:

| Gate | Tool | Scope | Result |
| --- | --- | --- | --- |
| Secrets | gitleaks | full git history, 147 commits | no leaks |
| SAST | Semgrep | 328 tracked files, 134 rules (OWASP Top 10, Java, Python, TS, Terraform + 8 project rules) | 0 findings |
| SCA, Java | Trivy | `mortgage-service`, `servicing-service` (transitive) | 0 vulnerabilities |
| SCA, npm | Trivy | `clients/mortgage-api-consumer`, `tests/e2e` (dev dependencies included) | 0 vulnerabilities |
| SCA, Python | pip-audit | analytics-service, knowledge-assistant (runtime + dev) | no known vulnerabilities |
| Containers | Trivy | the 4 service images, every CI run | no fixable CRITICAL (policy); last run PR #117 |

### M6 findings closure

| Severity (M6) | Findings | Status |
| --- | --- | --- |
| Critical | VULN-M6-002 no authentication; VULN-M6-018 dependencies with Critical CVEs | **Closed**: B-01, B-06c, with regression tests and the dependency gate |
| High | VULN-M6-001 mass assignment; -003 function-level authorization; -004 approver role from the body | **Closed**: B-02, B-03, B-04 (`RbacMatrixTest`, `MassAssignmentRegressionTest`, J4) |
| Medium | -005/-006/-007 throttling, uploads, query bounds; -008 PII to risk analysts; -009 default DB password; -010 shared HMAC key; -011 no revocation; -017 per-instance rate limits | Closed: B-05, B-06. **Accepted with conditions**: -010, -011, -017 ([register](../security/risk-register.md#risk-acceptance)); hardening B-09, B-10, B-11 open |
| Medium | -019 Spring Framework 6.2 CVEs without an open-source fix | **Exception** in `.trivyignore`, expires 2026-12-31; fixed by B-18 (Spring Boot 4) |
| Low | -012/-013/-014 headers, validation envelope, error leak; -015/-016 internal IDs, API docs | Closed: B-06b. Open: B-07, B-08 (P3, before a shared environment) |

No Critical or High finding is open.

## Performance smoke

`python3 scripts/perf/smoke.py`, 2026-11-11 00:15 UTC, local stack on the developer machine (Docker Desktop, Apple silicon). 4 read workers in a closed loop and 1 payment writer at 0.5/s for 120 s. Times are client-side wall time per request.

| Endpoint | Requests | Req/s | Errors | p50 ms | p95 ms | p99 ms | Max ms | Target |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET mortgage | 20,786 | 173 | 0 | 2.1 | 4.2 | 8.5 | 34.7 | |
| GET borrower's mortgages | 20,786 | 173 | 0 | 2.4 | 5.0 | 8.9 | 72.3 | |
| GET payments | 20,785 | 173 | 0 | 3.6 | 7.3 | 13.6 | 93.2 | |
| GET servicing history | 20,786 | 173 | 0 | 3.6 | 7.5 | 13.8 | 126.4 | |
| GET delinquency | 20,786 | 173 | 0 | 2.0 | 3.9 | 7.7 | 41.9 | |
| GET portfolio summary | 20,786 | 173 | 0 | 5.7 | 11.1 | 18.0 | 72.1 | p95 < 2 s (US-ANL-001): **met** |
| POST payment | 59 | 0.5 | 0 | 45.9 | 208.6 | 216.5 | 216.5 | p95 < 500 ms ([SLO](slo.md)): **met** |

- **Total:** 124,774 requests, about 1,040 a second, 0 non-2xx.
- **Event lag** (payment accepted → `PAYMENT_POSTED` in servicing-service, through SNS and SQS): 1,975, 117, 113, 114, 114 ms. The first sample includes the queue draining after the load. Target for the candidate event SLO: < 60 s.
- **Assistant** (real LLM, 5 policy questions): median 2.6 s, max 4.4 s, all 200 with 1–3 citations each. Dominated by the model call; there's no latency target for advisory answers.

**Limits of this result.** It's a baseline, not a capacity test: client and services share one machine, with no network in between, one replica per service, and a small seed database. In AWS the numbers will be different (network, Fargate CPU, RDS). Before go-live, repeat it against the target environment with production-sized data (C-5). Two known ceilings: write rate limits are per container (60 writes a minute per user), and they become per-cluster only with B-09.

## Backup and recovery

**Local check** (`bash scripts/ops/backup-restore-check.sh`, 2026-11-11 00:14 UTC): a `pg_dump` of `mortgage_intel` (566 KB, 1 s), restored into a scratch database (under 1 s), with every table's row count compared:

| Table | Rows | | Table | Rows |
| --- | --- | --- | --- | --- |
| app_user | 5 | | knowledge_chunk | 51 |
| borrower | 13 | | loan | 25 |
| delinquency | 10 | | mortgage | 26 |
| document | 13 | | payment | 1,188 |
| event_inbox | 1,221 | | servicing_history | 1,227 |
| idempotency_record | 1,175 | | | |

All 11 tables match. The scratch database and the dump file are deleted afterwards.

**What protects what:**

| Data | Protection | Recovery |
| --- | --- | --- |
| PostgreSQL (system of record) | Local: logical backups as above. **AWS: none yet**, because there's no RDS in the sandbox | C-2: RDS Multi-AZ, automated backups 7–35 days with point-in-time recovery; restore drill before go-live. Proposed targets: RPO 5 min, RTO 1 h |
| Events in flight | SQS retention and DLQs (`capstone-mortgage-*-dlq-dev`); consumers are idempotent (`event_inbox`) | Redrive from the DLQ ([messaging-runbook.md](messaging-runbook.md)) |
| Documents and analytics data (S3) | Encrypted (SSE), private buckets (M8); **no object versioning** | Curated analytics data is rebuilt by the Glue job from raw; a deleted document must be re-uploaded. Versioning or AWS Backup for the documents bucket is part of C-2 |
| Terraform state | Versioned S3 bucket, 30-day history, native locking | [Runbook: state damaged](runbook.md#rollback) |
| Container images | GHCR keeps every `sha-…`; dev ECR keeps 10 per service, immutable | Re-deploy any tag ([rollback](runbook.md#rollback)) |
| Knowledge base | Rebuilt from the corpus in Git (`docker compose run --rm knowledge-ingest`) | Re-ingest |
| Secrets | Not backed up by design: rotated and re-issued | [Runbook: secrets rotation](runbook.md#secrets-rotation) |

## Sign-off

- [x] Prepared and checked by the team (akr12403), 2026-11-11.
- [ ] **Reviewed by Sumanth Donur.** Tick when the review is done; the recommendation then stands as signed.

---

## Appendix: go-live recommendation

**Recommendation: GO with conditions.**

- **GO** for the capstone release `v1.0.0-capstone`: the platform as built, on synthetic data, in the local stack and the AWS dev environment. Every journey passes end to end, every gate is green, no Critical or High vulnerability is open, monitoring detected and the runbook resolved a simulated outage, and rollback has been exercised.
- **Not yet** for real borrower data or real users. The conditions below must be met first; they're the gap between a tested platform and an operated production service.

### Conditions before real data

| # | Condition | Why | Owner | Tracking |
| --- | --- | --- | --- | --- |
| C-1 | Spring Boot 4 migration in both Java services, removing the two `.trivyignore` exceptions | Spring Boot 3.5 gets no open-source fixes; the exceptions expire 2026-12-31 | Backend lead | B-18, R-17 |
| C-2 | Managed database: RDS Multi-AZ with automated backups and point-in-time recovery, versioning (or AWS Backup) for the documents bucket, and a restore drill | No database in AWS yet; one container database is a single point of failure | Platform lead | RCA P-6 |
| C-3 | Staff sign-in through the corporate identity provider with MFA; asymmetric tokens and revocation | Password-only login and a shared HMAC key are accepted only for the capstone | Security lead | B-15, B-10, B-11, R-01, R-04, R-05 |
| C-4 | CI deploys through OIDC, not a developer session | The sandbox policy blocks the OIDC provider; a human session deploys today | Platform lead | B-20, R-21 |
| C-5 | Performance test in the target environment with production-sized data; edge rate limiting | The smoke is a single-machine baseline; rate limits are per container | Platform lead | B-09, R-09 |
| C-6 | Logs and alerts in the organization's Splunk, with an on-call rotation | Local Splunk proves the setup; production needs the shared index and paging | Platform lead | [monitoring/splunk/README.md](../../monitoring/splunk/README.md) |

### Top 5 residual risks

| # | Risk | Residual | Owner | Mitigation in place | Next step |
| --- | --- | --- | --- | --- | --- |
| 1 | R-17 framework out of open-source support (Spring Boot 3.5 / Framework 6.2) | Medium (12), rising as unpatched CVEs appear | Backend lead | Newest 3.5 patch; affected features (XSLT, SSE views) unused; dependency gate | B-18 by 2026-12-31 (C-1) |
| 2 | Database outage or data loss (no managed database in AWS) | High for production; tested locally | Platform lead | Fail fast with 503 and alerts in 40 s ([RCA](rca-2026-11-10.md)); idempotent writes; local backup verified | RDS Multi-AZ + PITR (C-2) |
| 3 | R-01/R-04/R-05 account takeover or token misuse | Medium (10, 10, 8) | Security lead | Login rate limits, BCrypt, 1 h tokens, key ≥ 256 bit, rotation runbook | MFA, asymmetric keys, revocation (C-3) |
| 4 | R-21 AWS credentials misused (deploys from a developer session) | Medium (8) | Platform lead | Least-privilege workload roles, policy guard in CI, no access keys, deploys only of green images | OIDC deploy role (C-4) |
| 5 | R-18/R-19 staff act on a wrong AI answer, or personal data reaches the AI provider | Medium (8, 8) | AI lead | Similarity gate, citations checked in code, human approval for case actions, PII redaction, synthetic corpus, J5 in CI | Production corpus review and provider data agreement before real documents |

### Rollback plan for the release

1. **Image rollback** (minutes): `bash scripts/deploy/deploy-dev.sh <previous tag>`, or for the release `v1.0.0-capstone-rc1`'s images (`sha-<rc1 commit>`). Same tested images, no rebuild ([runbook](runbook.md#rollback)).
2. **Stop traffic** if the service itself is unsafe: scale the ECS services to 0 (`desired_count = 0` in `tfvars`, apply). That's the current state in dev.
3. **Data:** restore the database from the last backup or snapshot (local: `pg_restore` as in the check above; AWS after C-2: RDS point-in-time restore), then redrive the DLQs.
4. **Code:** `git revert` the release merge and let the pipeline re-run.

### Support and escalation

| Level | Who | Responsibility | Contact |
| --- | --- | --- | --- |
| L1 | Support / on-call engineer | Triage with the dashboard and the alert's runbook section; restart, scale or roll back per the runbook | GitHub issue in `akr12403/mortgage-platform` with label `incident` |
| L2 | Platform and backend lead (akr12403) | Diagnosis by `correlationId`, fixes, deploys, rollbacks, RCA | GitHub `@akr12403` |
| SME | Security lead (akr12403), AI lead (akr12403), reviewer (Sumanth Donur) | Security incidents and key rotation; assistant answers; review of changes | Escalate through L2 |

Severity levels and timelines are in [incident-response.md](incident-response.md#severity). The handover checklist is in [kt-checklist.md](kt-checklist.md).
