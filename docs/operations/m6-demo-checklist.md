# M6 Demo & Sign-off Checklist

Automated demo: `bash scripts/m6-demo.sh` (about 10 minutes; `PAUSE=1` waits for Enter before each step, for rehearsal). It follows the milestone's demo scenario step by step.

## Before the demo

```bash
cd ~/projects/mortgage-platform
docker compose up --build -d && docker compose ps   # all services healthy
PAUSE=1 bash scripts/m6-demo.sh
```

Have these open in a browser tab: [threat-model.md](../security/threat-model.md) (step 4) and the merged PR #90 → **Checks** tab on GitHub (step 5).

## Demo scenario (maps to the milestone's demo script)

| # | Show (time) | What to say | Pass criteria |
| --- | --- | --- | --- |
| 1 | **Login as SERVICING_AGENT; GET servicing history** (2 min) | Login returns an HS256 JWT with `sub`, `roles`, `iss`, `exp`; 1 h TTL; BCrypt passwords. The same token works on servicing-service: one issuer, and every service checks signature, issuer and expiry. | no token → 401; JWT claims shown (never the token); with Bearer → 200 and the history events |
| 2 | **Same token on a restricted POST → 403** (2 min) | `POST /mortgages` is ORIGINATION-only (ADMIN, UNDERWRITER). Enforcement is server-side and deny-by-default, and 403 comes before validation. Also SUPPORT approving a loan (M10 Journey 4). | both calls → 403 `ACCESS_DENIED` in the shared error envelope |
| 3 | **Run the TS consumer** (2 min) | Token in memory only; Bearer on every call; a 401 triggers one re-login and one retry; a 403 is never retried; HTTPS is required off localhost. | login → GET mortgage → GET servicing history → 401 → re-login → retry OK → 403 surfaced |
| 4 | **Walk one STRIDE threat and its mitigation** (3 min) | T-06 *Tampering*: mass assignment on payment post (VULN-M6-001). Before: the body was bound to the entity, so a client-sent `id` overwrote a payment. After: the `PaymentRequest` DTO. Show Diagram 3 and the T-06 row, then the regression tests. | threat → impact → mitigation → evidence, tied to the payment-post data flow |
| 5 | **Show the pipeline security jobs passing** (1 min) | Three blocking gates (gitleaks over full history, Semgrep, Trivy + pip-audit), defined once in `scripts/security-gates.sh` and run by GitHub Actions and GitLab. PR #91 shows the secret gate failing. | PR #90 checks all green; the script's live secret gate and self-test PASS |

## Validation (from the milestone)

- [x] **Login returns JWT; protected endpoint works with Bearer token.** `test_auth_smoke.py` 7/7 and `JwtAuthenticationTest`; demo step 1
- [x] **SUPPORT cannot call underwriter-only endpoint (403).** `RbacMatrixTest::supportCannotApproveLoan_M10Journey4`, `test_rbac_smoke.py::test_support_cannot_approve_loan_m10_journey4`; demo step 2
- [x] **TS consumer completes login + GET flow.** `npm test` 16/16 and `npm run demo` against the live stack (2026-10-24); demo step 3
- [ ] **Threat model and risk register reviewed by peer.** Reviewer: **Sumanth Donur**, review due **2026-11-10**. Tick this box and the sign-off boxes in [threat-model.md](../security/threat-model.md#sign-off) and [risk-register.md](../security/risk-register.md#review)
- [x] **No Critical open vulnerabilities in report.** [vulnerability-report.md](../security/vulnerability-report.md#summary): 0 Critical/High open
- [x] **Pipeline fails on intentional test secret (then remove).** PR #91: `secret-detection` failed in 8 s, closed unmerged, branch deleted ([evidence](./devsecops-baseline.md#validation-the-pipeline-fails-on-an-intentional-test-secret))

## Definition of Done → evidence

| DoD item | Evidence |
| --- | --- |
| Authentication implemented | `POST /api/v1/auth/login`, BCrypt seed users: [authentication.md](../security/authentication.md); `AuthApiTest`, `AuthServiceTest` |
| JWT validation on protected APIs | all three services validate signature, `iss` and `exp`; `alg:none`, wrong key, expired and tampered tokens → 401: `JwtAuthenticationTest`, `JwtValidationTest`, analytics `test_rbac.py` |
| RBAC implemented and tested for all five roles | [RBAC matrix](../security/security-controls.md#rbac-matrix); `RbacMatrixTest` (every endpoint × 5 roles) in both Java services, `test_rbac.py`, `test_rbac_smoke.py` |
| Sensitive endpoints protected | borrower PII limited to `BORROWER_PII_READ`; names hidden from RISK_ANALYST (VULN-M6-008); deny-by-default; only health and login are public |
| OWASP controls applied (validation, headers, rate limit) | [OWASP API Top 10 section](../security/security-controls.md#owasp-api-security-top-10-task-63); `InputValidationTest`, `SecurityHeadersTest`, `RateLimitTest`, `test_owasp.py`, `test_owasp_smoke.py` 8/8 |
| Encryption and classification documented | [classification](../security/security-controls.md#data-classification-task-65), [encryption + KMS plan](../security/security-controls.md#encryption-task-65), [secrets rotation runbook](./runbook.md#secrets-rotation) |
| TypeScript API consumer demonstrated | [clients/mortgage-api-consumer](../../clients/mortgage-api-consumer/README.md); live run 2026-10-24; demo step 3 |
| Threat model completed (STRIDE) | [threat-model.md](../security/threat-model.md): 25 threats, annotated M1 deployment diagram, document-upload and payment-post data flows |
| Risk register and vulnerability report completed | [risk-register.md](../security/risk-register.md) (17 risks, heat map, acceptances), [vulnerability-report.md](../security/vulnerability-report.md) (19 findings), [remediation-backlog.md](../security/remediation-backlog.md) |
| Critical vulnerabilities remediated | VULN-M6-002 (no auth) and VULN-M6-018 (Tomcat/Netty CVEs) fixed with commit links; 0 Critical open |
| Secure CI gates configured (SAST/SCA/secrets) | [devsecops-baseline.md](./devsecops-baseline.md#security-gates-task-67); `.github/workflows/security-gates.yml`, `.gitlab-ci.yml`; green on PR #90 |
| Merged to develop via reviewed PR(s) | PR #90 (Tasks 6.1–6.7) and the sign-off PR merged into `develop` with all three required gates green. Solo project: no second developer to approve, so human review is the instructor's (see the Validation item above) |

## Known limits (stated, not hidden)

- GitHub branch protection is configured but **not enforced** on this free private repository. The gates still run and fail visibly, and enforcement needs an organization plan (M9). See [devsecops-baseline.md](./devsecops-baseline.md#repository-security-settings-github).
- Two Spring Framework 6.2 CVEs with no open-source fix on the 3.5 line are **accepted until 2026-12-31** (VULN-M6-019). The Spring Boot 4 migration is planned for M9 (B-18).
- Single shared HMAC key and no token revocation: accepted for M6 (R-04, R-05), with RS256/JWKS and a `jti` deny-list planned for M9.
