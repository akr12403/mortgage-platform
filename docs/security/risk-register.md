# Security Risk Register (M6 Task 6.6)

Threats come from the [threat model](./threat-model.md) (`T-xx`), and findings from the [vulnerability report](./vulnerability-report.md). Fixes are scheduled in the [remediation backlog](./remediation-backlog.md).

**Scoring.** Likelihood (L) and Impact (I) are each 1–5, and Score = L × I. Bands: **15–25 High · 8–14 Medium · 1–7 Low**. *Inherent* is the score with no controls (end of M5). *Residual* is the score with the controls built in M6, assuming the planned AWS controls are in place before real data is loaded.

**Owners** are team roles. On a small team one person can hold several roles; the role is what gets reviewed.

| Role | Covers |
| --- | --- |
| Security lead | auth model, threat model, risk acceptance |
| Backend lead | mortgage-service and servicing-service |
| Analytics lead | analytics-service and documents |
| Platform lead | AWS, Terraform, CI/CD, secrets |
| AI lead | knowledge assistant, prompts, corpus, AI provider (M7) |

## Register

| ID | Risk | Threats / findings | Inherent L×I | Controls in place | Residual L | Residual I | Residual score | Owner | Status | Review |
| --- | --- | --- | :-: | --- | :-: | :-: | :-: | --- | --- | --- |
| R-01 | Account takeover through password guessing or credential stuffing on login | T-02 · VULN-M6-005 | 4×5 = **20** | login rate limits (per account and per IP), BCrypt(12), uniform errors and timing | 2 | 5 | 10 Medium | Security lead | Mitigated. MFA through the corporate identity provider before go-live | M9 |
| R-02 | A user acts outside their role, or reads data outside their duties | T-09 T-23 · VULN-M6-003 | 4×4 = **16** | 5-role RBAC on every route, deny by default, matrix tests in all services | 1 | 4 | 4 Low | Security lead | Mitigated. Revisit if a borrower-facing role is added (needs ownership checks) | each new endpoint |
| R-03 | Forged access token accepted | T-05 · VULN-M6-002 | 3×5 = **15** | HS256 pinned, ≥256-bit key from env, issuer and expiry checks, `alg:none` rejected | 1 | 5 | 5 Low | Security lead | Mitigated | M9 |
| R-04 | A compromised service mints tokens with the shared HMAC key | T-20 · VULN-M6-010 | 2×5 = 10 | one trust zone with the same deployment controls; key only in env/Secrets Manager; 90-day rotation | 2 | 5 | 10 Medium | Security lead | **Accepted for M6.** Move to RS256/ES256 + JWKS (backlog B-10) | M9 |
| R-05 | A stolen token is used until it expires | T-01 T-03 · VULN-M6-011 | 3×4 = 12 | 1 h TTL, HTTPS only, in-memory token handling in clients, emergency revoke by key rotation | 2 | 4 | 8 Medium | Security lead | **Accepted for M6.** `jti` deny-list + shorter TTL with refresh (B-11) | M9 |
| R-06 | Financial records altered or duplicated through the payment API | T-06 T-07 · VULN-M6-001 | 4×5 = **20** | DTO binding, `Idempotency-Key` with fingerprint, bean validation bounds, write rate limit | 1 | 5 | 5 Low | Backend lead | Mitigated | M10 |
| R-07 | Actions cannot be attributed (approvals, payments) | T-08 T-19 · VULN-M6-004 | 3×4 = 12 | approver role from the JWT; `user` and `correlationId` on every log line and event | 1 | 4 | 4 Low | Backend lead | Mitigated. Central log retention in M9 | M9 |
| R-08 | Underwriting documents leaked, or a malicious file stored | T-11 T-15 T-35 T-36 · VULN-M6-006 | 4×5 = **20** | type allowlist + magic bytes, size limit, safe keys, RBAC on upload; M8: Block Public Access, ACLs off, SSE-S3, TLS-only bucket policy, write-only upload role, Lambda re-validation | 1 | 5 | 5 Low | Analytics lead | Partial. Bucket controls done (M8). Open: malware scan before staff download (B-13), SSE-KMS via Terraform (B-12) | M9 |
| R-09 | Service unavailable through request flooding or expensive queries | T-04 T-10 · VULN-M6-007 VULN-M6-017 | 4×3 = 12 | page and date-range bounds, upload limit, per-user write limits | 3 | 3 | 9 Medium | Platform lead | Partial. WAF rate-based rules + shared rate-limit store (B-09) | M9 |
| R-10 | Borrower PII shown to roles without need-to-know | T-12 · VULN-M6-008 | 3×4 = 12 | names only for `BORROWER_PII_READ`; field-level classification; PII-free events | 1 | 4 | 4 Low | Analytics lead | Mitigated (Task 6.6) | each new endpoint |
| R-11 | SQL injection | T-13 | 3×5 = **15** | parameterised queries only, static SQL guard test, ID patterns | 1 | 5 | 5 Low | Backend lead | Mitigated | every PR (test) |
| R-12 | Database or secrets exposed (stolen snapshot, default or committed password) | T-14 T-21 · VULN-M6-009 | 3×5 = **15** | no default secrets (startup fails), `.env` git-ignored, secret scanning, rotation runbook; planned: KMS-encrypted RDS, TLS `verify-full`, Secrets Manager rotation | 2 | 5 | 10 Medium | Platform lead | Partial. AWS controls in M9 Terraform (B-12) | M9 |
| R-13 | Forged, tampered or poison events corrupt servicing data | T-16 T-17 | 2×4 = 8 | publish rights only for mortgage-service, schema validation, dedupe, DLQ after 3 receives | 1 | 4 | 4 Low | Backend lead | Mitigated. IAM topic policy in M9 Terraform | M9 |
| R-14 | PII or tokens written to logs | T-18 | 3×4 = 12 | logging rules (IDs and usernames only), no bodies or tokens logged, KMS log groups planned | 2 | 4 | 8 Medium | Platform lead | Partial. Automated log-redaction check in CI (B-14) | M9 |
| R-15 | Reconnaissance helped by public API docs, internal IDs and server banners | T-22 · VULN-M6-015 VULN-M6-016 | 3×2 = 6 | deny-by-default routes, generic errors | 3 | 2 | 6 Low | Analytics lead | Open (B-07, B-08) | before the first shared environment |
| R-16 | Supply-chain compromise through dependencies or the pipeline | T-24 | 3×5 = **15** | protected branches and review (M2), pinned versions, lockfile for the TS client, blocking CI gates: gitleaks, Semgrep, Trivy, pip-audit (6.7) | 2 | 5 | 10 Medium | Platform lead | Mitigated (Task 6.7): secret, SAST and dependency gates on every PR ([devsecops-baseline.md](../operations/devsecops-baseline.md)). Merge blocking isn't enforced by GitHub on this free private repository (accepted below); image/IaC scanning and digest pinning in M9 | M9 |
| R-17 | Framework line out of open-source support: Spring Boot 3.5 / Spring Framework 6.2 / Spring Security 6.5 get no further OSS patches after June 2026 | VULN-M6-018 VULN-M6-019 | 4×4 = **16** | newest available 3.5.16; Tomcat pinned to the current 10.1.x; dependency gate reports every new HIGH/CRITICAL | 3 | 4 | 12 Medium | Backend lead | Open. Migrate to Spring Boot 4.x (B-18); until then the gate flags any new Critical and the PR is blocked | M9 |
| R-18 | Staff act on a wrong or fabricated AI answer (hallucination, prompt injection, poisoned corpus, over-trusted incident advice) | T-26 T-27 T-31 T-32 | 4×4 = **16** | per-question similarity gate, context-only prompt, strict JSON, citation verification, insufficient-context reply, code-decided `requiresHumanApproval`, reviewed and versioned corpus; [governance.md](../ai/governance.md) | 2 | 4 | 8 Medium | AI lead | Mitigated (M7). Approval rules are keyword-based; graded answer-evaluation set in M10 | M10 |
| R-19 | Personal data disclosed to the external AI provider | T-28 | 4×4 = **16** | synthetic corpus, PII and secret redaction before every LLM call, business ids only, no prompt or answer logging, user rule in the security policy | 2 | 4 | 8 Medium | AI lead + security lead | Partial: names and addresses are not detectable by pattern. Before any real data: a named-entity redactor and a data-processing agreement with the provider | before real data |
| R-20 | AI API key leak or cost abuse | T-29 T-30 | 3×3 = 9 | restricted project key with allowed models, expiry, spend alert, prepaid balance without auto-reload, env-only storage, gitleaks, per-user rate limit, LLM skipped for off-corpus questions | 1 | 3 | 3 Low | Platform lead | Mitigated (M7). Secrets Manager move deferred to M9: in M8 the services still run locally, so the key stays in the git-ignored `.env` | M9 |
| R-21 | AWS credentials or roles misused (compromised workload or developer session) | T-33 T-34 | 4×5 = **20** | least-privilege role per workload, policy guard in CI, Access Analyzer + 39 simulator cases, no access keys anywhere, 1-hour workload sessions, MFA browser sign-in, project guardrails | 2 | 4 | 8 Medium | Platform lead | Mitigated for workloads (M8). Partial: deployments run with the developer's admin session. The scoped OIDC CI roles (B-20) are implemented but blocked by the sandbox SCP (no OIDC provider allowed). Interim control: `scripts/deploy/deploy-dev.sh` deploys only images with a green `ci` run, and applies only a plan shown first. | M9 |
| R-22 | Analytics report wrong, incomplete or silently changed (pipeline defect, tampering, schema drift) | T-37 T-38 | 3×4 = 12 | single writer for curated, checks before writes, schema contract, fail-with-alert drift policy, reconciliation 8 checks with documented tolerances | 1 | 4 | 4 Low | Analytics lead | Mitigated (M8). Source data-quality issues are reported as WARN (B-19) | M9 |
| R-23 | Decisions made on a stale DynamoDB lookup value | T-39 | 3×3 = 9 | conditional event updates, DLQ on failure, freshness fields in every response, PostgreSQL authoritative | 2 | 2 | 4 Low | Analytics lead | Mitigated (M8). Rule: money-moving actions read PostgreSQL, never the cache | M10 |
| R-24 | Cloud cost overrun or orphaned resources and data | T-40 | 3×3 = 9 | Free plan, tags, on-demand capacity, retention limits, `teardown.sh` | 1 | 2 | 2 Low | Platform lead | Mitigated (M8). Teardown after M8 sign-off; budget alarms with the M9 account | M8 sign-off |

## Heat map (residual)

| Impact ↓ / Likelihood → | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| **5** | R-03 R-06 R-08 R-11 | R-01 R-04 R-12 R-16 | | | |
| **4** | R-02 R-07 R-10 R-13 R-22 | R-05 R-14 R-18 R-19 R-21 | R-17 | | |
| **3** | R-20 | | R-09 | | |
| **2** | R-24 | R-23 | R-15 | | |

No residual risk is in the High band.

## Risk acceptance

| Risk | Accepted by | Rationale | Conditions | Expires |
| --- | --- | --- | --- | --- |
| R-04 shared HMAC key | Security lead | Three internal services in one trust zone; asymmetric keys add a JWKS endpoint and key distribution, which belong with the M9 platform work | key ≥ 256 bit, Secrets Manager only, 90-day rotation, compromise playbook in the runbook | go-live (renewed at the M10 readiness review, 2026-11-11; replaced by B-10) |
| R-05 no token revocation | Security lead | 1 h TTL bounds the window; a key rotation revokes everything in an emergency | HTTPS only; clients keep tokens in memory | go-live (renewed at the M10 readiness review, 2026-11-11; replaced by B-11) |
| VULN-M6-017 per-instance rate limits (part of R-09) | Platform lead | correct for the single-instance stack | must be replaced before horizontal scaling | first multi-replica deploy |
| GitHub branch protection not enforced (part of R-16) | Platform lead | private repository on a free personal plan: GitHub stores the rules but does not enforce them. The gates still run and fail visibly on every PR | team rule: never merge a PR with a red security check; rules take effect unchanged on a public repository or a Team/Enterprise organization | move to an organization plan (M9) |
| VULN-M6-019 Spring Framework 6.2 CVE-2026-47884 / CVE-2026-47890 (part of R-17) | Backend lead + security lead | no open-source 6.2.x fix; vendor rates Medium/Low; `XsltView` and SSE view fragments are not used | no views, XSLT or SSE may be added; the `.trivyignore` entries carry `exp:2026-12-31`, after which the gate fails | 2026-12-31 or the Spring Boot 4 migration (B-18), whichever comes first |

## Review

- Reviewed at every milestone sign-off, and whenever an endpoint, role or data store is added.
- M10 readiness review, 2026-11-11: residual scores unchanged; R-04 and R-05 acceptances renewed to go-live; the top 5 residual risks and the go-live conditions are in [production-readiness.md](../operations/production-readiness.md#appendix-go-live-recommendation).
- [x] Peer review: Sumanth Donur, due 2026-11-10 (tick when done) **Done: reviewed and approved by Sumanth Donur, 2026-11-10.**
- [ ] Instructor review (date)
