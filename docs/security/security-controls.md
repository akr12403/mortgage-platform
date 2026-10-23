# Security Controls

Covers M6 **Task 6.2 (RBAC)**. Data classification and encryption (Task 6.5) will be added to this file. Authentication: [authentication.md](./authentication.md).

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
