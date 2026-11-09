# Remediation Backlog (M6 Task 6.6)

Prioritised fixes for the findings in the [vulnerability report](./vulnerability-report.md) and the open risks in the [risk register](./risk-register.md). **Critical and High items link to the commit that fixed them.**

**Priority:** P0 = Critical, fixed before anything else · P1 = High, fixed in the same milestone · P2 = Medium, fixed or risk-accepted with a date · P3 = Low or hardening, scheduled.

## Done

| ID | Pri | Finding | Fix | Commit | Regression test |
| --- | --- | --- | --- | --- | --- |
| B-01 | **P0** | VULN-M6-002 no authentication (Critical) | JWT login, token validation in all services | [`a7600e4`](https://github.com/akr12403/mortgage-platform/commit/a7600e4), [`a42e350`](https://github.com/akr12403/mortgage-platform/commit/a42e350) | `JwtAuthenticationTest`, `JwtValidationTest`, `test_rbac.py`, `test_auth_smoke.py` |
| B-02 | **P1** | VULN-M6-003 no function-level authorization (High) | 5-role RBAC, deny by default, 403 `ACCESS_DENIED` | [`a42e350`](https://github.com/akr12403/mortgage-platform/commit/a42e350) | `RbacMatrixTest` ×2, `test_rbac.py`, `test_rbac_smoke.py` |
| B-03 | **P1** | VULN-M6-004 approver role from the request body (High) | role taken from the JWT | [`a42e350`](https://github.com/akr12403/mortgage-platform/commit/a42e350) | `RbacMatrixTest`, `MortgageApiTest` |
| B-04 | **P1** | VULN-M6-001 mass assignment on payments (High) | `PaymentRequest` DTO | [`8ec934e`](https://github.com/akr12403/mortgage-platform/commit/8ec934e) | `MassAssignmentRegressionTest`, `test_owasp_smoke.py` |
| B-05 | P2 | VULN-M6-005/006/007 login throttling, upload restrictions, query bounds | rate limits, upload limits and checks, page and date limits | [`8ec934e`](https://github.com/akr12403/mortgage-platform/commit/8ec934e) | `RateLimitTest`, `InputValidationTest`, `test_owasp.py`, `test_owasp_smoke.py` |
| B-06 | P2 | VULN-M6-008 PII to RISK_ANALYST; VULN-M6-009 default DB password | names only for `BORROWER_PII_READ`; no default secrets, fail fast | Task 6.6 commit on `feature/M6-task6` | `test_data_protection.py`, `SecretConfigurationTest` ×2, `test_rbac_smoke.py` |
| B-06c | **P0** | VULN-M6-018 dependencies with Critical CVEs (Tomcat 10.1.20; netty-handler on 3.5.16) | Spring Boot 3.2.5 → 3.5.16, Tomcat 10.1.61, Netty 4.1.139, Jackson 2.21.7, pgjdbc 42.7.14 | Task 6.7 commit on `feature/M6-task7` | `dependency-scanning` gate, full Java suites |
| B-06b | P3 | VULN-M6-012/013/014 headers, validation envelope, storage error leak | header set, 400 envelope, generic 502 | [`8ec934e`](https://github.com/akr12403/mortgage-platform/commit/8ec934e) | `SecurityHeadersTest`, `SecurityHardeningTest`, `test_owasp.py` |

## Open (ordered by priority)

| ID | Pri | Item | Finding / risk | Acceptance criteria | Owner | Target |
| --- | --- | --- | --- | --- | --- | --- |
| B-12 | P2 | AWS data-protection controls as code (S3 Block Public Access, TLS-only policy and SSE-S3 applied by script in M8): RDS KMS encryption + `rds.force_ssl` + `sslmode=verify-full`; S3 Block Public Access, SSE-KMS default and TLS-only policy; SNS/SQS SSE; Secrets Manager with rotation | R-08, R-12 | Terraform plan shows each control; a policy check (e.g. tfsec/Checkov) fails the build if one is removed | Platform lead | M8/M9 |
| B-09 | P2 | Move rate limiting to the edge (WAF rate-based rules) or a shared store | R-09, VULN-M6-017 | limits hold across ≥ 2 replicas in a load test | Platform lead | M9 |
| B-10 | P2 | Asymmetric JWTs: RS256/ES256 with a JWKS endpoint; validators hold only public keys; `kid` for zero-downtime rotation | R-04, VULN-M6-010 | servicing and analytics cannot sign; a key rotation causes no forced logout | Security lead | M9 |
| B-11 | P2 | Token revocation: `jti` deny-list checked on each request, 15-min access tokens + refresh tokens | R-05, VULN-M6-011 | a revoked token gets 401 within seconds; the TS client's refresh path is covered by tests | Security lead | M9 |
| B-13 | P2 | Malware scanning of uploaded documents before staff can download them | R-08 | an EICAR test file is quarantined and never served | Analytics lead | M9 (moved from M8: no scanning service on the Free plan; Lambda type re-validation added in M8) |
| B-14 | P2 | CI check that logs contain no PII or tokens (log-redaction test on a sample run) | R-14 | the pipeline fails when a test log contains an email, a JWT or a seed name | Platform lead | M9 |
| B-15 | P2 | MFA for staff via the corporate identity provider (OIDC) | R-01 | the login flow requires a second factor for all roles | Security lead | before go-live |
| B-16 | P2 | SAST, SCA and secret-scanning gates that block merge on Critical findings | R-16 | an intentional test secret fails the pipeline (M6 validation item) | Platform lead | **Done (Task 6.7):** gates green on PR #90, the secret gate failed on the intentional secret in PR #91 ([evidence](../operations/devsecops-baseline.md#pipeline-evidence-redacted-screenshot)). GitHub enforcement of the required checks needs an organization plan (M9) |
| B-07 | P3 | Remove internal UUIDs (`id`) from API responses (v1 → v2 or additive deprecation) | VULN-M6-015, R-15 | responses carry business IDs only; OpenAPI and Postman updated | Backend lead | M9 |
| B-08 | P3 | Analytics: disable `/docs`, `/redoc` and `/openapi.json` unless `ENABLE_API_DOCS=true`; uvicorn `--no-server-header` | VULN-M6-016, R-15 | the docs return 404 by default; no `server` header | Analytics lead | before the first shared environment |
| B-18 | P2 | Migrate both Java services to Spring Boot 4.x (Spring Framework 7, Spring Security 7, Jackson 3) so framework patches stay open source | R-17, VULN-M6-018, VULN-M6-019 | all test suites green; the dependency gate passes **with the two Spring `.trivyignore` entries removed** | Backend lead | M9, and before **2026-12-31**, when the exceptions expire |
| B-17 | P3 | Field-level KMS envelope encryption for `date_of_birth` (and any future SSN) | R-12, [classification](./security-controls.md#encryption-task-65) | a DB dump shows ciphertext only for Restricted columns | Backend lead | before real data |
| B-19 | P3 | Severity refresh: re-evaluate `delinquency.severity` from days past due (30–59 MODERATE, 60–89 SEVERE, 90+ CRITICAL) and correct mislabelled rows such as MTG-1005 (88 days, `CRITICAL`) | R-22, reconciliation `DQ_SEVERITY_BAND` | `reconcile.sh` reports no `DQ_SEVERITY_BAND` warnings on the seed data | Backend lead | M9 |
| B-21 | P3 | Pin Python dependencies with a lock file (exact versions + hashes) for analytics-service and knowledge-assistant, so every image build installs the same packages | R-16 | two builds a week apart produce identical `pip freeze`; the container scan result does not change between them | Platform lead | M9 |
| B-20 | P2 | CI deploy role: GitHub/GitLab OIDC → an IAM role with permissions scoped to the M8/M9 resources, replacing deploys from the developer's admin session | R-21 | a pipeline run deploys the stack; the developer session is needed only for break-glass | Platform lead | M9 |

## Rules

- A new Critical finding goes straight to P0 and blocks the milestone sign-off until it is fixed and has a regression test.
- Closing an item needs the fixing commit, a test that fails without the fix, and the status updated in the vulnerability report and risk register.
- Risk acceptance (instead of fixing) is recorded in the risk register with an owner and an expiry.
