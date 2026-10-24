# Security Controls

Covers M6 **Task 6.2 (RBAC)** and **Task 6.3 (OWASP API Top 10 hardening)**. Data classification and encryption (Task 6.5) will be added to this file. Authentication: [authentication.md](./authentication.md).

## Roles

Role codes come from `guides/standards.md` and travel in the JWT `roles` claim.

| Role | Code | Seed user | Job (from `docs/requirements/personas.md`) |
| --- | --- | --- | --- |
| Administrator | `ADMIN` | `admin@capstone.local` | full access, user and role provisioning |
| Underwriter | `UNDERWRITER` | `underwriter@capstone.local` | onboard borrowers, create mortgages, approve or decline loans |
| Servicing agent | `SERVICING_AGENT` | `servicing@capstone.local` | post payments, run delinquency, servicing notes and history |
| Risk analyst | `RISK_ANALYST` | `risk@capstone.local` | portfolio and delinquency analytics, read-only |
| Support | `SUPPORT` | `support@capstone.local` | read-only troubleshooting; used for deny tests |

## RBAC matrix

✓ = allowed, ✗ = 403 `ACCESS_DENIED`. Every row also requires a valid token: no token gets 401 `UNAUTHORIZED`, and a bad or expired token gets 401 `INVALID_TOKEN`.

### mortgage-service (:8080)

| Endpoint | ADMIN | UNDERWRITER | SERVICING_AGENT | RISK_ANALYST | SUPPORT | Group |
| --- | :-: | :-: | :-: | :-: | :-: | --- |
| `POST /api/v1/auth/login` | public | public | public | public | public | — |
| `POST /api/v1/borrowers` | ✓ | ✓ | ✗ | ✗ | ✗ | ORIGINATION |
| `GET /api/v1/borrowers/{id}` (PII) | ✓ | ✓ | ✓ | ✗ | ✗ | BORROWER_PII_READ |
| `POST /api/v1/mortgages` | ✓ | ✓ | ✗ | ✗ | ✗ | ORIGINATION |
| `GET /api/v1/mortgages/{id}`, `GET /api/v1/mortgages?borrowerId=` | ✓ | ✓ | ✓ | ✓ | ✓ | ALL_ROLES |
| `POST /api/v1/mortgages/{id}/underwriting-decision` (loan approval) | ✓ | ✓ | ✗ | ✗ | ✗ | ORIGINATION |
| `GET /api/v1/mortgages/{id}/payments` | ✓ | ✓ | ✓ | ✓ | ✓ | ALL_ROLES |
| `POST /api/v1/mortgages/{id}/payments` | ✓ | ✗ | ✓ | ✗ | ✗ | SERVICING_WRITE |
| `POST /api/v1/delinquency-evaluations` (delinquency write) | ✓ | ✗ | ✓ | ✗ | ✗ | SERVICING_WRITE |

### servicing-service (:8081)

| Endpoint | ADMIN | UNDERWRITER | SERVICING_AGENT | RISK_ANALYST | SUPPORT | Group |
| --- | :-: | :-: | :-: | :-: | :-: | --- |
| `GET /api/v1/mortgages/{id}/servicing-history` | ✓ | ✓ | ✓ | ✓ | ✓ | ALL_ROLES |
| `GET /api/v1/mortgages/{id}/delinquency` | ✓ | ✓ | ✓ | ✓ | ✓ | ALL_ROLES |
| `POST /api/v1/mortgages/{id}/servicing-events` | ✓ | ✗ | ✓ | ✗ | ✗ | SERVICING_WRITE |

### mortgage-analytics-service (:8000)

| Endpoint | ADMIN | UNDERWRITER | SERVICING_AGENT | RISK_ANALYST | SUPPORT | Group |
| --- | :-: | :-: | :-: | :-: | :-: | --- |
| `GET /api/v1/analytics/*` (portfolio, delinquency, borrower risk, payment trends, event stats) | ✓ | ✓ | ✗ | ✓ | ✗ | ANALYTICS_READ |
| `POST /api/v1/documents/upload` | ✓ | ✓ | ✓ | ✗ | ✗ | DOCUMENT_UPLOAD |

Health endpoints (`/actuator/health`, `/actuator/info`, `/health`) stay public for container health checks.

This matches the milestone's example rows: `POST /mortgages` allows ADMIN and UNDERWRITER only; `GET servicing-history` allows all five roles; delinquency writes allow ADMIN and SERVICING_AGENT.

### Why these choices

- **Least privilege on PII.** Borrower records hold name, email, phone and date of birth, so only roles that deal with individual borrowers can read them. RISK_ANALYST works on aggregates through analytics, and SUPPORT troubleshoots with mortgage, payment and servicing views that carry business IDs, not personal details.
- **Separation of duties.** Underwriters originate and approve. Servicing agents move money (payments) and manage delinquency. Neither can do the other's job; only ADMIN can do both.
- **The approver is recorded from the token.** `approvedByRole` on `LoanApproved` comes from the caller's JWT (UNDERWRITER, else ADMIN). The request body can no longer claim a role.
- **Read-only roles stay read-only.** RISK_ANALYST and SUPPORT have no write permission anywhere.

## How it is enforced (server-side only)

| Service | Mechanism |
| --- | --- |
| mortgage-service, servicing-service | URL-level rules in `SecurityConfig` (`requestMatchers(...).hasAnyRole(...)`), using role groups from `security/Rbac.java` |
| analytics-service | FastAPI router dependency `require_roles(...)` in `src/api/security.py` (PyJWT, HS256 pinned) |

- **Authorization runs before request validation.** A forbidden caller always gets 403, never a 400 that reveals what a valid body looks like. `wrongRoleIsRejectedBeforeValidation` tests this.
- **Deny by default.** Any route without an explicit rule (`anyRequest().denyAll()`) is refused, so a new endpoint is closed until someone adds it to this matrix.
- **Unknown or missing roles** (for example a token whose `roles` claim is empty or `GUEST`) are denied everywhere.
- Role checks happen only on the server. Clients, including the Task 6.4 TypeScript client, may hide buttons, but they are never trusted.
- 403 responses use the shared envelope with code **`ACCESS_DENIED`**, the code expected by M10 Journey 4.

## Tests

| Test | What it proves |
| --- | --- |
| `mortgage-service` `RbacMatrixTest` | every endpoint × all 5 roles: allowed → 2xx, denied → 403 `ACCESS_DENIED`; SUPPORT cannot approve a loan (M10 J4); 403 comes before validation; GUEST role denied; unmapped route denied |
| `servicing-service` `RbacMatrixTest` | 3 endpoints × 5 roles; unmapped route denied |
| `analytics` `tests/test_rbac.py` | 4 read endpoints and upload × 5 roles; missing, expired, wrong-key, wrong-issuer, `alg:none` and garbage tokens → 401 |
| `tests/security/test_rbac_smoke.py` | live stack: real logins for all five seed users against representative allow/deny cells in all three services |

When an endpoint is added or changed, update this matrix, `Rbac.java` / `security.py`, and the matrix tests in the same PR.

## OWASP API Security Top 10 (Task 6.3)

Review of all three services against the [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/). Each row names the control and the test that proves it.

| # | Risk | Control in this repo | Evidence |
| --- | --- | --- | --- |
| API1 | Broken object level authorization | Every route needs a valid JWT and a role from the RBAC matrix above. Records are addressed by business IDs, never internal UUIDs. Per-borrower ownership checks are not needed yet: there is no borrower-facing role, and all five roles are staff with portfolio-wide jobs. | `RbacMatrixTest` (both services), `tests/test_rbac.py` |
| API2 | Broken authentication | HS256 JWT with pinned algorithm, issuer and expiry checks; BCrypt(12) passwords; generic `INVALID_CREDENTIALS`; **login rate limit** (per account and per IP) | `JwtAuthenticationTest`, `AuthApiTest`, `RateLimitTest`, `test_auth_smoke.py`, `test_owasp_smoke.py::test_login_is_rate_limited` |
| API3 | Broken object property level authorization (mass assignment, over-exposure) | Request bodies bind to DTOs (`MortgageCreateRequest`, `BorrowerRequest`, `PaymentRequest`, `UnderwritingDecisionRequest`) that contain only client-writable fields. **VULN-M6-001 fixed** (below). Responses use DTOs or `@JsonBackReference` so no internal graph leaks. | `MassAssignmentRegressionTest`, `test_owasp_smoke.py::test_payment_body_cannot_choose_the_payment_id` |
| API4 | Unrestricted resource consumption | Page size 1–100; payment-trends range at most 3660 days; amounts and lengths bounded; uploads limited to 10 MB (early `Content-Length` check plus bounded read); **rate limits** on writes (60/min/user), logins and uploads (20/min/user) | `InputValidationTest`, `RateLimitTest`, `SecurityHardeningTest`, `tests/test_owasp.py` |
| API5 | Broken function level authorization | URL-level rules with `anyRequest().denyAll()`; analytics routers carry `require_roles`. Write operations are limited to the roles that own them. | `RbacMatrixTest::unmappedRouteIsDeniedByDefault`, `test_rbac_smoke.py` |
| API6 | Unrestricted access to sensitive business flows | Loan approval and payment posting are role-restricted, payments need an `Idempotency-Key` for safe retries (1–255 chars), and writes are rate limited per user | `RbacMatrixTest`, `MassAssignmentRegressionTest::oversizedIdempotencyKey_IsRejected` |
| API7 | Server-side request forgery | No endpoint fetches a client-supplied URL. S3 keys are built only from validated parts (`MTG-####`, a UUID, the sanitised filename). | code review; `test_valid_upload_succeeds_with_sanitised_key` |
| API8 | Security misconfiguration | Security headers on every response, errors included (table below). The error envelope never carries stack traces, SQL or AWS details. Analytics returns 400 `VALIDATION_ERROR` in the same envelope instead of FastAPI's raw 422. Secrets come from env only. | `SecurityHeadersTest`, `SecurityHardeningTest`, `tests/test_owasp.py`, `test_owasp_smoke.py` |
| API9 | Improper inventory management | Three OpenAPI specs in `docs/api/` list every route, its roles (`x-roles`) and its 4xx/429 responses. Deny-by-default closes any route not in the matrix. | `docs/api/*-openapi.yaml` |
| API10 | Unsafe consumption of APIs | Events from SQS are validated against JSON Schemas and deduplicated on `eventId`. Poison messages go to the DLQ after 3 receives (M5). | `EventSchemaContractTest`, `tests/contract/test_event_contracts.py`, `EventConsumerServiceTest` |

### Injection (SQL and others)

- **SQL**: all statements use bound parameters: Spring Data/JPQL derived queries, `JdbcTemplate` with `?`, SQLAlchemy `text()` with `:name`. `tests/security/test_static_sql.py` fails the build if any source concatenates, f-strings, `%`-formats or `.format()`s SQL. The test checks itself against a known-bad sample, so a broken regex cannot pass silently.
- Live probes (`' OR '1'='1`, `UNION SELECT …`) come back as an ordinary 404 for an unknown ID, and the table is still intact afterwards (`test_owasp_smoke.py::test_sql_injection_probes_are_plain_values`).
- Business IDs are validated with patterns (`MTG-\d{4}`, `BOR-\d{3}`, `LOAN-\d{4}`) at the API edge in all services.
- **File uploads**: content type must be on an allowlist (PDF, PNG, JPEG, plain text) and must match the file's magic bytes, otherwise 415. Filenames are stripped of paths and unsafe characters (`../../etc/passwd` → `passwd`). The mortgage must exist **before** anything is written to S3.

### VULN-M6-001: mass assignment on payment creation (fixed)

| | |
| --- | --- |
| Found | M6 Task 6.3 review, `POST /api/v1/mortgages/{id}/payments` |
| Severity | High: integrity of financial records (OWASP API3) |
| Cause | The controller bound the JSON body directly onto the `Payment` JPA entity. A client could send `"id"` of an existing payment, and `save()` then **merged** (overwrote) that row: changing its amount or status, or moving it between mortgages. |
| Fix | New `PaymentRequest` DTO with only `dueDate`, `paidDate`, `amount` and `status` (bounded: 0.01–10,000,000.00, 2 decimals, status enum). `toNewEntity()` always creates a fresh entity, and the mortgage comes only from the URL. Unknown JSON properties are ignored. |
| Regression tests | `MassAssignmentRegressionTest` (unit: the bound entity has a null id and mortgage) and `test_owasp_smoke.py::test_payment_body_cannot_choose_the_payment_id` (live: the targeted payment is unchanged and a new ID is issued) |

### Security headers

| Header | Value | Services |
| --- | --- | --- |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` (looser policy only for analytics `/docs`, `/redoc` and `/openapi.json`, so Swagger UI works) | all |
| `X-Content-Type-Options` | `nosniff` | all |
| `X-Frame-Options` | `DENY` | all |
| `Referrer-Policy` | `no-referrer` | all |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=(), payment=(), usb=()` | all |
| `Cross-Origin-Resource-Policy` | `same-origin` | all |
| `Cache-Control` | `no-cache, no-store, max-age=0, must-revalidate` (Java) / `no-store` (analytics) | all |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains`, sent only over HTTPS (TLS terminates at the load balancer in M9) | Java services |

### Rate limits

| Scope | Limit (per minute) | Where | Env var |
| --- | --- | --- | --- |
| Login per (client IP, username) | 10 | `AuthController` | `RATE_LIMIT_LOGIN_PER_USER` |
| Login per client IP | 60 | `RateLimitFilter` (mortgage-service) | `RATE_LIMIT_LOGIN_PER_IP` |
| Writes (POST/PUT/PATCH/DELETE) per user | 60 | `RateLimitFilter` (both Java services) | `RATE_LIMIT_WRITES_PER_USER` |
| Document uploads per user | 20 | `documents.py` | `RATE_LIMIT_UPLOADS_PER_USER` |

Over the limit the response is **429 `RATE_LIMITED`** in the shared envelope with a `Retry-After` header. The client IP is the socket address; `X-Forwarded-For` is deliberately **not** trusted, because a client could forge it to dodge the per-IP limit.

**Known limit:** the counters are fixed-window and in-memory per container. That is correct for this single-instance stack, but with N replicas the effective limit is N× and counters reset on restart. M9 moves throttling to a shared store (Redis/ElastiCache) or the API gateway / AWS WAF rate-based rules, and the proxy's client-IP header is trusted only once there is a known proxy in front.

### Task 6.3 tests

| Test | What it proves |
| --- | --- |
| `mortgage-service` `MassAssignmentRegressionTest` | VULN-M6-001 stays fixed; payment amount and Idempotency-Key bounds |
| `mortgage-service` `InputValidationTest` | cross-field and bounds validation on mortgages and borrowers, page-size limits, malformed JSON → 400 envelope, SQL-injection path probe → plain 404 |
| `mortgage-service` `RateLimitTest`, `RateLimiterTest` | login per account and per IP, writes per user, 429 + `Retry-After`; limiter window logic |
| `mortgage-service` `SecurityHeadersTest`, `servicing-service` `SecurityHardeningTest` | headers on error responses, HSTS only over HTTPS, servicing write throttling |
| `analytics` `tests/test_owasp.py`, `tests/test_hardening_units.py` | headers, 400 envelope, date and ID validation, upload size/type/filename/ordering, upload rate limit, no storage-detail leaks |
| `tests/security/test_static_sql.py` | no string-built SQL in any service |
| `tests/security/test_owasp_smoke.py` | the same controls against the live stack |
