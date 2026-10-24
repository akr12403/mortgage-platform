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
| R-08 | Underwriting documents leaked, or a malicious file stored | T-11 T-15 · VULN-M6-006 | 4×5 = **20** | type allowlist + magic bytes, size limit, safe keys, RBAC on upload; planned: Block Public Access, SSE-KMS, TLS-only bucket policy | 2 | 5 | 10 Medium | Analytics lead | Partial. Bucket controls in M8/M9 Terraform (B-12); malware scan before staff download (B-13) | M8 |
| R-09 | Service unavailable through request flooding or expensive queries | T-04 T-10 · VULN-M6-007 VULN-M6-017 | 4×3 = 12 | page and date-range bounds, upload limit, per-user write limits | 3 | 3 | 9 Medium | Platform lead | Partial. WAF rate-based rules + shared rate-limit store (B-09) | M9 |
| R-10 | Borrower PII shown to roles without need-to-know | T-12 · VULN-M6-008 | 3×4 = 12 | names only for `BORROWER_PII_READ`; field-level classification; PII-free events | 1 | 4 | 4 Low | Analytics lead | Mitigated (Task 6.6) | each new endpoint |
| R-11 | SQL injection | T-13 | 3×5 = **15** | parameterised queries only, static SQL guard test, ID patterns | 1 | 5 | 5 Low | Backend lead | Mitigated | every PR (test) |
| R-12 | Database or secrets exposed (stolen snapshot, default or committed password) | T-14 T-21 · VULN-M6-009 | 3×5 = **15** | no default secrets (startup fails), `.env` git-ignored, secret scanning, rotation runbook; planned: KMS-encrypted RDS, TLS `verify-full`, Secrets Manager rotation | 2 | 5 | 10 Medium | Platform lead | Partial. AWS controls in M9 Terraform (B-12) | M9 |
| R-13 | Forged, tampered or poison events corrupt servicing data | T-16 T-17 | 2×4 = 8 | publish rights only for mortgage-service, schema validation, dedupe, DLQ after 3 receives | 1 | 4 | 4 Low | Backend lead | Mitigated. IAM topic policy in M9 Terraform | M9 |
| R-14 | PII or tokens written to logs | T-18 | 3×4 = 12 | logging rules (IDs and usernames only), no bodies or tokens logged, KMS log groups planned | 2 | 4 | 8 Medium | Platform lead | Partial. Automated log-redaction check in CI (B-14) | M9 |
| R-15 | Reconnaissance helped by public API docs, internal IDs and server banners | T-22 · VULN-M6-015 VULN-M6-016 | 3×2 = 6 | deny-by-default routes, generic errors | 3 | 2 | 6 Low | Analytics lead | Open (B-07, B-08) | before the first shared environment |
| R-16 | Supply-chain compromise through dependencies or the pipeline | T-24 | 3×5 = **15** | protected branches and review (M2), pinned versions, lockfile for the TS client, blocking CI gates: gitleaks, Semgrep, Trivy, pip-audit (6.7) | 2 | 5 | 10 Medium | Platform lead | Mitigated (Task 6.7): secret, SAST and dependency gates on every PR ([devsecops-baseline.md](../operations/devsecops-baseline.md)). Merge blocking isn't enforced by GitHub on this free private repository (accepted below); image/IaC scanning and digest pinning in M9 | M9 |
| R-17 | Framework line out of open-source support: Spring Boot 3.5 / Spring Framework 6.2 / Spring Security 6.5 get no further OSS patches after June 2026 | VULN-M6-018 VULN-M6-019 | 4×4 = **16** | newest available 3.5.16; Tomcat pinned to the current 10.1.x; dependency gate reports every new HIGH/CRITICAL | 3 | 4 | 12 Medium | Backend lead | Open. Migrate to Spring Boot 4.x (B-18); until then the gate flags any new Critical and the PR is blocked | M9 |

## Heat map (residual)

| Impact ↓ / Likelihood → | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| **5** | R-03 R-06 R-11 | R-01 R-04 R-08 R-12 R-16 | | | |
| **4** | R-02 R-07 R-10 R-13 | R-05 R-14 | R-17 | | |
| **3** | | | R-09 | | |
| **2** | | | R-15 | | |

No residual risk is in the High band.

## Risk acceptance

| Risk | Accepted by | Rationale | Conditions | Expires |
| --- | --- | --- | --- | --- |
| R-04 shared HMAC key | Security lead | Three internal services in one trust zone; asymmetric keys add a JWKS endpoint and key distribution, which belong with the M9 platform work | key ≥ 256 bit, Secrets Manager only, 90-day rotation, compromise playbook in the runbook | M9 sign-off |
| R-05 no token revocation | Security lead | 1 h TTL bounds the window; a key rotation revokes everything in an emergency | HTTPS only; clients keep tokens in memory | M9 sign-off |
| VULN-M6-017 per-instance rate limits (part of R-09) | Platform lead | correct for the single-instance stack | must be replaced before horizontal scaling | first multi-replica deploy |
| GitHub branch protection not enforced (part of R-16) | Platform lead | private repository on a free personal plan: GitHub stores the rules but does not enforce them. The gates still run and fail visibly on every PR | team rule: never merge a PR with a red security check; rules take effect unchanged on a public repository or a Team/Enterprise organization | move to an organization plan (M9) |
| VULN-M6-019 Spring Framework 6.2 CVE-2026-47884 / CVE-2026-47890 (part of R-17) | Backend lead + security lead | no open-source 6.2.x fix; vendor rates Medium/Low; `XsltView` and SSE view fragments are not used | no views, XSLT or SSE may be added; the `.trivyignore` entries carry `exp:2026-12-31`, after which the gate fails | 2026-12-31 or the Spring Boot 4 migration (B-18), whichever comes first |

## Review

- Reviewed at every milestone sign-off, and whenever an endpoint, role or data store is added.
- [ ] Peer review (date, reviewer)
- [ ] Instructor review (date)
