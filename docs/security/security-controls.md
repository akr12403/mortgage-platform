# Security Controls

Covers M6 **Task 6.2 (RBAC)**, **Task 6.3 (OWASP API Top 10 hardening)** and **Task 6.5 ([data classification](#data-classification-task-65) and [encryption](#encryption-task-65))**. Secrets rotation: [runbook](../operations/runbook.md#secrets-rotation). Authentication: [authentication.md](./authentication.md).

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
| `GET /api/v1/lookup/mortgages/{id}` (M8, DynamoDB cache: status, balance, no PII) | ✓ | ✓ | ✓ | ✓ | ✗ | LOOKUP_READ |

### mortgage-knowledge-assistant (:8001, M7)

| Endpoint | ADMIN | UNDERWRITER | SERVICING_AGENT | RISK_ANALYST | SUPPORT | Group |
| --- | :-: | :-: | :-: | :-: | :-: | --- |
| `POST /api/v1/assistant/ask` | ✓ | ✓ | ✓ | ✓ | ✓ | ASSISTANT_ASK |
| `POST /api/v1/assistant/summarize-incident` (Task 7.6) | ✓ | ✗ | ✗ | ✗ | ✗ | INCIDENT_SUMMARIZE |

Every staff role may ask: the corpus is synthetic **Internal** policy text and the endpoint returns no borrower data. Incident summaries read operational logs, so only the on-call ADMIN may request them. Same JWT validation as analytics (`src/api/security.py`, HS256 pinned, issuer and expiry required); tests in `ai/mortgage-knowledge-assistant/tests/test_api.py`. Answers are advisory; case decisions are flagged `requiresHumanApproval` (`docs/ai/governance.md`).

Health endpoints (`/actuator/health`, `/actuator/info`, `/health`, and the assistant's `/health/ready`) stay public for container health checks.

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
| Assistant questions / incident summaries per user (each may cost an LLM call; separate counters) | 20 | `src/api/main.py` (knowledge assistant) | `RATE_LIMIT_ASSISTANT_PER_USER` |

Over the limit the response is **429 `RATE_LIMITED`** in the shared envelope with a `Retry-After` header. The client IP is the socket address; `X-Forwarded-For` is deliberately **not** trusted, because a client could forge it to dodge the per-IP limit.

**Known limit:** the counters are fixed-window and in-memory per container. That is correct for this single-instance stack, but with N replicas the effective limit is N× and counters reset on restart. M9 moves throttling to a shared store (Redis/ElastiCache) or the API gateway / AWS WAF rate-based rules, and the proxy's client-IP header is trusted only once there is a known proxy in front.

### Security tests (Tasks 6.3–6.6)

| Test | What it proves |
| --- | --- |
| `mortgage-service` `MassAssignmentRegressionTest` | VULN-M6-001 stays fixed; payment amount and Idempotency-Key bounds |
| `mortgage-service` `InputValidationTest` | cross-field and bounds validation on mortgages and borrowers, page-size limits, malformed JSON → 400 envelope, SQL-injection path probe → plain 404 |
| `mortgage-service` `RateLimitTest`, `RateLimiterTest` | login per account and per IP, writes per user, 429 + `Retry-After`; limiter window logic |
| `mortgage-service` `SecurityHeadersTest`, `servicing-service` `SecurityHardeningTest` | headers on error responses, HSTS only over HTTPS, servicing write throttling |
| `analytics` `tests/test_owasp.py`, `tests/test_hardening_units.py` | headers, 400 envelope, date and ID validation, upload size/type/filename/ordering, upload rate limit, no storage-detail leaks |
| `tests/security/test_static_sql.py` | no string-built SQL in any service |
| `tests/security/test_owasp_smoke.py` | the same controls against the live stack |
| `analytics` `tests/test_data_protection.py`, `SecretConfigurationTest` ×2 (Task 6.6) | DP-GAP-1 (no names for RISK_ANALYST) and DP-GAP-2 (no default secrets) stay fixed |
| `clients/mortgage-api-consumer` `npm test` (Task 6.4) | the client side of the contract: Bearer on every call, 401 → one re-login + one retry, 403 never retried, 429 honours `Retry-After`, token never in logs or errors, HTTPS required off localhost |

## Data classification (Task 6.5)

All data in this repository and in every non-production environment is **synthetic** (`docs/requirements/project-scope.md`). The classification below describes how the platform must treat the **real** equivalent, and the controls are built to that level now.

### Levels

| Level | Meaning | Examples here | Handling |
| --- | --- | --- | --- |
| **Public** | Approved for anyone; disclosure causes no harm | `/health` and `/actuator/health` responses, published product information | No restrictions beyond integrity |
| **Internal** | For staff and systems; low harm if leaked | business IDs (`BOR-###`, `MTG-####`), statuses, aggregates, staff usernames and roles, API specs, architecture docs | Authenticated access; may appear in logs, events and tickets |
| **Confidential** | Personal or financial information about an identifiable borrower (PII / nonpublic personal information) | names, email, phone, loan terms, balances, payments, delinquency | RBAC need-to-know, encrypted in transit and at rest, **never in logs, events, URLs or AI prompts**; masked outside production |
| **Restricted** | Severe harm if leaked: enables identity theft, account takeover or forging access | date of birth, uploaded documents (pay stubs, W-2s, tax returns), password hashes, JWTs, signing keys, DB and cloud credentials | Everything required for Confidential, plus the smallest possible set of roles or systems, KMS-encrypted storage with audited key use, never exported to analytics or non-production, rotation on suspicion |

A record takes the **highest** level of any field it contains. A combination can raise the level: a business ID on its own is Internal, but a borrower risk summary that joins it to a name and balances is Confidential.

### Borrower and loan data, field by field

| Table.column | Level | Notes |
| --- | --- | --- |
| `borrower.id`, `borrower.borrower_external_id` | Internal | pseudonymous keys; they reveal nothing without the borrower table |
| `borrower.first_name`, `borrower.last_name` | **Confidential** | direct identifiers |
| `borrower.email`, `borrower.phone` | **Confidential** | contact PII |
| `borrower.date_of_birth` | **Restricted** | identity-verification attribute; combined with a name it is enough for most identity fraud |
| `borrower.created_at` | Internal | |
| `mortgage.mortgage_external_id`, `mortgage.status` | Internal on its own; **Confidential** once linked to a borrower | `DELINQUENT` is adverse credit information about a person |
| `mortgage.original_amount`, `mortgage.outstanding_balance`, `mortgage.origination_date` | **Confidential** | personal financial information |
| `loan.loan_external_id` | Internal | |
| `loan.interest_rate`, `loan.term_months`, `loan.underwriting_decision` | **Confidential** | credit decision about a person |
| `payment.*` (dates, amount, status) | **Confidential** | payment history |
| `idempotency_record.request_fingerprint` | **Confidential** | plain-text copy of the payment fields (amount, dates, status) |
| `servicing_history.event_type`, `event_time` | Internal | |
| `servicing_history.description` | **Confidential** | free-text notes. Rule: agents must not type Restricted data (DOB, SSN, account numbers) into notes |
| `delinquency.*` | **Confidential** | days past due and severity are credit information |
| `document.document_type`, `document.created_at` | Internal | |
| `document.file_name`, `document.s3_key` | **Confidential** | file names often contain the borrower's name |
| Document **contents** in S3 | **Restricted** | pay stubs, W-2s and tax returns carry SSN, income and employer |
| `app_user.username`, `app_user.roles`, `app_user.enabled` | Internal | staff identity, not borrower data |
| `app_user.password_hash` | **Restricted** | BCrypt(12); never returned by any API or logged |
| `event_inbox.*` | Internal | event IDs and timestamps only |

**Deliberately not collected:** SSN or tax IDs, bank account or card numbers, and income as structured fields. These exist only inside uploaded documents (Restricted), which keeps most of the database at Confidential.

### Data outside the database

| Asset | Level | Rule |
| --- | --- | --- |
| Domain events on SNS/SQS | Confidential (financial amounts) | Payloads carry **business IDs only**, never names, contact details or DOB. Enforced by the JSON Schemas in `docs/architecture/events/` and `EventSchemaContractTest`; adding a PII field to an event requires a schema change and review. |
| API responses | level of the highest field | `GET /borrowers/{id}` is Restricted (DOB), so it is limited to `BORROWER_PII_READ`; mortgage, payment and servicing views are Confidential; analytics aggregates are Internal |
| Application logs | must stay **Internal** | Logs carry correlation ID, user (a staff username), business IDs, event IDs and counts. They never carry request bodies, tokens, passwords, names, emails or amounts. |
| Access tokens (JWT) | Restricted while valid | held in memory by clients (`clients/mortgage-api-consumer`); 1 h TTL; never logged |
| Secrets (`JWT_SECRET`, DB passwords, `AUTH_SEED_PASSWORD`, AWS credentials) | Restricted | env / Secrets Manager only; rotation in the [runbook](../operations/runbook.md#secrets-rotation) |
| OpenAPI specs, event catalog, these docs | Internal | |
| AI assistant prompts (M7) | must stay Internal | no Confidential or Restricted fields in prompts, per trust boundary TB-4 |

### Known gaps found during classification (Task 6.6 status)

| ID | Gap | Why it matters | Status |
| --- | --- | --- | --- |
| DP-GAP-1 | `GET /api/v1/analytics/borrowers/{id}/risk-summary` returned `firstName`/`lastName` to `RISK_ANALYST` | Contradicted the least-privilege rule above | **Fixed (VULN-M6-008):** names only for `BORROWER_PII_READ` roles |
| DP-GAP-2 | The DB password had code defaults (`postgres` in the Java `application.yml`, `change-me` in analytics) | A misconfigured deployment would start with a guessable credential | **Fixed (VULN-M6-009):** no defaults anywhere; services and compose fail fast |
| DP-GAP-3 | API responses include internal UUIDs (`id`) next to business IDs | Not sensitive in itself, but it leaks internal structure | **Open (VULN-M6-015):** [backlog B-07](./remediation-backlog.md) |

## Encryption (Task 6.5)

### In transit

The path follows the trust boundaries in [`trust-boundaries.md`](../architecture/trust-boundaries.md) and the topology in [`deployment-architecture.md`](../architecture/deployment-architecture.md).

| Hop | Boundary | Production (M9) | Local Docker (today) |
| --- | --- | --- | --- |
| Client → edge | TB-1 | **TLS terminates at the public ALB** (per the M1 deployment doc). Certificates from ACM with automatic renewal; security policy `ELBSecurityPolicy-TLS13-1-2-2021-06` (TLS 1.3, 1.2 fallback, no TLS 1.0/1.1); port 80 only redirects to 443; AWS WAF in front. The services add HSTS (`max-age=31536000; includeSubDomains`) on HTTPS responses (Task 6.3). | plain HTTP on `localhost` only. The TS client refuses plain HTTP to any non-local host. |
| ALB → services | TB-2 | **Re-encrypted**: HTTPS target groups, with each service serving TLS on its app port (Spring `server.ssl.*`, uvicorn `--ssl-*`, certificate from AWS Private CA). Services sit in private subnets and their security groups accept only the ALB. That satisfies the "TLS for all traffic across trust boundaries" rule, so the internal network is never trusted on its own. | HTTP on the compose network |
| Service → PostgreSQL (RDS) | TB-3 | TLS required on both sides: the RDS parameter `rds.force_ssl=1`, and clients use `sslmode=verify-full` with the RDS CA bundle (JDBC `?sslmode=verify-full&sslrootcert=…`, psycopg `sslmode=verify-full`) | unencrypted on the private compose network |
| Service → S3 / SNS / SQS | TB-3 | AWS SDK over HTTPS through VPC endpoints. Bucket and queue policies **deny** any request with `aws:SecureTransport = false`. | LocalStack over HTTP |
| Service → service (events) | TB-3 | through SNS/SQS only (above); no direct service-to-service calls today. If any are added, they use mTLS. | LocalStack |

The local exceptions are acceptable only because local data is synthetic and never leaves the machine. Do not point a local stack at real data.

### At rest

| Store | Data level | Encryption | Notes |
| --- | --- | --- | --- |
| RDS PostgreSQL (all tables) | up to Restricted (DOB, password hashes) | **RDS storage encryption with a customer-managed KMS key** `alias/capstone-<env>-rds`; automated backups, snapshots and read replicas inherit it | Encryption must be enabled **at creation**: it cannot be switched on later without snapshot → encrypted copy → restore. Snapshots are shared only with re-encryption under the target account's key. |
| S3 document bucket | Restricted | **SSE-KMS** default bucket encryption with `alias/capstone-<env>-documents` and S3 Bucket Keys; Block Public Access on; versioning; the bucket policy denies uploads without `aws:kms` and any non-TLS access | The upload code (`s3_service.py`) relies on the bucket default, so there is no per-object encryption setting to forget |
| SNS topic and SQS queues (+ DLQs) | Confidential | SSE with `alias/capstone-<env>-messaging` | the key policy lets only the publisher and consumers use it |
| Secrets (JWT signing key, DB credentials) | Restricted | AWS Secrets Manager, encrypted with `alias/capstone-<env>-secrets` | injected as env at task start; see the [runbook](../operations/runbook.md#secrets-rotation) |
| CloudWatch Logs | Internal | KMS-encrypted log groups (`alias/capstone-<env>-logs`) | logs must not contain Confidential data in the first place |
| Container storage (ECS/Fargate ephemeral, EBS) | transient | encrypted by default (AWS-managed keys) | services keep no data on local disk; uploads are streamed to S3 |
| M8 data lake / exports | Internal (aggregates) | SSE-KMS; Restricted columns (DOB, documents) are **excluded** from exports | M8 data platform buckets |
| Passwords | Restricted | **hashed, not encrypted**: BCrypt cost 12 | cannot be decrypted, by design |
| Local Docker volume `pgdata` | synthetic only | not encrypted by the stack | rely on host disk encryption (FileVault / BitLocker) |

**Column-level encryption:** today, `date_of_birth` is protected by RDS storage encryption plus RBAC (`BORROWER_PII_READ`), not by field-level encryption. Storage encryption protects disks, snapshots and backups, but not a compromised app or a SQL account with SELECT. Before real data is loaded, encrypt `date_of_birth` (and any SSN, if one is ever collected) in the application with KMS envelope encryption (a data key per record, wrapped by `alias/capstone-<env>-pii`), so a DB dump alone exposes no Restricted values. This is a planned item, not built.

### Production WAF rules: request process

AWS WAF in front of the public ALB is part of the M9 deployment. M6 records how rules get requested and changed, so the edge is never edited ad hoc.

**Baseline web ACL (M9, Terraform):**
- AWS managed rule groups: `AWSManagedRulesCommonRuleSet`, `AWSManagedRulesKnownBadInputsRuleSet`, `AWSManagedRulesSQLiRuleSet` and `AWSManagedRulesAmazonIpReputationList`;
- a **rate-based rule** on `POST /api/v1/auth/login` per client IP, which complements the in-app limits above (B-09).

**Requesting a new or changed rule:**

1. The service owner opens a ticket stating the purpose, scope (host, path, method), match conditions, expected traffic and false-positive risk, and the rollback.
2. The **security lead** and **platform lead** review it. A rule that could block legitimate borrower traffic also needs the product owner's agreement.
3. The rule is added in Terraform and deployed in **COUNT** mode to the test environment for at least 7 days. The sampled requests are checked for false positives.
4. It is promoted to **BLOCK** through the normal reviewed PR and pipeline, and the change is recorded in the runbook change log.
5. **Emergency block** (an active attack): the platform lead may apply an IP set or rate rule directly, and it must be back in Terraform with a post-incident review within 2 working days.

### KMS key plan

| Alias | Protects | Key users (IAM roles) | Key admins |
| --- | --- | --- | --- |
| `alias/capstone-<env>-rds` | RDS storage, snapshots | RDS service | platform admins (no decrypt) |
| `alias/capstone-<env>-documents` | S3 documents | analytics-service task role | platform admins |
| `alias/capstone-<env>-messaging` | SNS, SQS, DLQs | mortgage-service (publish), servicing and analytics (consume) | platform admins |
| `alias/capstone-<env>-secrets` | Secrets Manager entries | each service reads only its own secrets | security team |
| `alias/capstone-<env>-logs` | CloudWatch log groups | CloudWatch Logs | platform admins |
| `alias/capstone-<env>-pii` (planned) | field-level DOB / SSN encryption | mortgage-service only | security team |

- Customer-managed keys, **one set per environment**: a dev key can never decrypt prod data.
- **Automatic annual key rotation** is enabled. AWS keeps the old key material, so existing data stays readable and needs no re-encryption.
- Key administrators and key users are separate roles; no human role has `kms:Decrypt` on prod keys in normal operation.
- Every `Decrypt`/`GenerateDataKey` call is logged in CloudTrail. Unusual use (a new principal, volume spikes) alerts the security team (M9 observability).
- Deleting a key uses the 30-day waiting period and requires two-person approval, because deleting a key destroys its data.
