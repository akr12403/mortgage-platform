# Authentication (M6 Task 6.1)

## Approach

**Login against seed users with a self-issued JWT** (the first option in Task 6.1): `mortgage-service` hosts `POST /api/v1/auth/login`, checks the password against a BCrypt hash in `app_user`, and returns a signed **HS256 JWT**. servicing-service and mortgage-analytics-service validate that token on every protected request with the same shared secret and issuer (analytics since Task 6.2).

We chose this over an external OAuth2/OIDC provider (Keycloak, Cognito, Ping) because the capstone needs a working login with no extra infrastructure. The rest of the design does not depend on that choice: tokens carry standard claims and are validated with Spring Security's Nimbus decoder. Moving to a real IdP later means swapping the issuer, plus moving from HS256 to RS256 validated against the provider's JWKS. Controllers stay the same. Full Ping/SailPoint integration is out of scope for M6.

```text
client ──POST /api/v1/auth/login {username,password}──> mortgage-service
        <── 200 {accessToken, tokenType:"Bearer", expiresInSeconds, roles} ──
client ──GET/POST … Authorization: Bearer <jwt>──> mortgage-service :8080 / servicing-service :8081
                                                    JwtAuthenticationFilter: signature ✓ exp ✓ iss ✓ → ROLE_<role>
```

## Token

| Claim | Value |
| --- | --- |
| `sub` | username, e.g. `servicing@capstone.local` |
| `roles` | e.g. `["SERVICING_AGENT"]`, mapped to Spring authorities `ROLE_SERVICING_AGENT`; drives RBAC ([security-controls.md](./security-controls.md)) |
| `iss` | `capstone-mortgage-auth` (`JWT_ISSUER`); other issuers are rejected |
| `exp` | issue time + `JWT_TTL_SECONDS` (default 3600). **Mandatory**: tokens without `exp` are rejected; 30 s clock skew allowed |
| `iat`, `jti` | issue time, unique token ID (for audit and future revocation) |

- Algorithm: HS256. The key comes from `JWT_SECRET`, which must be at least 32 bytes (256 bits). Startup **fails** if the secret is missing or short. Generate one with `openssl rand -base64 48`.
- No refresh token. When the token expires, the client gets `401 INVALID_TOKEN` and logs in again. The Task 6.4 TypeScript client implements that retry.
- No server-side sessions (`SessionCreationPolicy.STATELESS`).

## Route protection

| Service | Public | Everything else |
| --- | --- | --- |
| mortgage-service | `GET /actuator/health/**`, `GET /actuator/info`, `POST /api/v1/auth/login` | valid Bearer token required |
| servicing-service | `GET /actuator/health/**`, `GET /actuator/info` | valid Bearer token required |
| analytics-service | `GET /health` | valid Bearer token required (PyJWT, HS256 pinned; added in Task 6.2) |
| knowledge-assistant (M7) | `GET /health`, `GET /health/ready` | valid Bearer token required (same PyJWT validation; `POST /api/v1/assistant/ask`) |

Every `/api/v1/mortgages/**` mutation requires an authenticated user, as the M6 checklist demands. Per-role rules (Task 6.2) are in [security-controls.md](./security-controls.md); routes without a rule are denied by default.

## Responses

| Situation | Status | `code` | Extra |
| --- | --- | --- | --- |
| No `Authorization` header on a protected route | 401 | `UNAUTHORIZED` | `WWW-Authenticate: Bearer` |
| Malformed, tampered, wrong-key, wrong-issuer or expired token | 401 | `INVALID_TOKEN` | `WWW-Authenticate: Bearer error="invalid_token"` |
| Wrong username, password, or disabled account | 401 | `INVALID_CREDENTIALS` | same response for all three (no user enumeration) |
| Authenticated but the role is not allowed (Task 6.2) | 403 | `ACCESS_DENIED` | |

All use the shared envelope `{code, message, correlationId, timestamp}`.

## Spring Security checklist (from the milestone)

- [x] `SecurityFilterChain` with the JWT filter added **before** `UsernamePasswordAuthenticationFilter` (`SecurityConfig`)
- [x] CSRF disabled for stateless APIs. CSRF abuses credentials the browser sends automatically (cookies or sessions). This API uses neither: the token is sent explicitly in the `Authorization` header, which a cross-site form or image request cannot set. If cookie-based auth is ever added, CSRF protection must be turned back on.
- [x] Public: `/actuator/health`, `/api/v1/auth/login`
- [x] All `/api/v1/mortgages/**` mutations require an authenticated user (in fact, all non-public routes do)

## Passwords and secrets

- Passwords are stored only as **BCrypt (cost 12)** hashes in `app_user.password_hash` (migration `004_app_user.sql`).
- The five standard seed users (`admin@`, `underwriter@`, `servicing@`, `risk@`, `support@capstone.local`) are created on first startup from **`AUTH_SEED_PASSWORD`**, a local `.env` value of at least 12 characters that is never committed. No hashes or passwords are in Git.
- `JWT_SECRET` and `AUTH_SEED_PASSWORD` come from the environment only. `docker compose` refuses to start without them.
- Unknown-user logins still run a BCrypt check against a dummy hash, so response time does not reveal which usernames exist.
- Never logged: passwords, tokens, `Authorization` headers. Failed logins are logged at WARN with a sanitized username (CR/LF stripped). Log lines include `user=<sub>` for authenticated requests.
- Login responses send `Cache-Control: no-store`. Responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`. Task 6.3 adds CSP, Permissions-Policy, CORP and HSTS (over HTTPS), and login throttling: 10 attempts per minute per (client IP, username) and 60 per minute per client IP, answered with 429 `RATE_LIMITED` and `Retry-After`. See [security-controls.md](./security-controls.md#owasp-api-security-top-10-task-63).

## Rotating the JWT secret

Change `JWT_SECRET` in the environment for **all three** services (mortgage-service issues tokens; servicing-service and analytics-service validate them) and restart them. Step-by-step: [runbook → JWT signing key](../operations/runbook.md#jwt-signing-key-jwt_secret). Every outstanding token becomes invalid immediately, and clients log in again. Zero-downtime rotation (accept old and new keys during a grace period using `kid`) is described as future work in the [runbook](../operations/runbook.md#zero-downtime-key-rotation-future).

## Verify

```bash
cp .env.example .env    # then set JWT_SECRET and AUTH_SEED_PASSWORD
docker compose up --build -d
python3 tests/security/test_auth_smoke.py      # runs against the live stack (stdlib only)
python3 tests/security/test_rbac_smoke.py      # real logins for all five roles vs the RBAC matrix
bash scripts/m5-demo.sh                        # step 0b shows 401 without a token, then logs in
```

Unit and integration tests: `JwtAuthenticationTest`, `AuthApiTest`, `AuthServiceTest`, `JwtKeysTest` (mortgage-service) and `JwtValidationTest` (servicing-service).

## Consuming the API from a client (Task 6.4)

[`clients/mortgage-api-consumer/`](../../clients/mortgage-api-consumer/README.md) is the reference TypeScript client.

1. `POST /api/v1/auth/login` → keep `accessToken` **in memory**, along with `expiresInSeconds`. Never write it to disk, `localStorage` or logs.
2. Send `Authorization: Bearer <token>` (plus `X-Correlation-Id`) to any service.
3. There are no refresh tokens. Log in again shortly before expiry. On a **401**, discard the token, log in **once** and retry **once**; if it fails again, surface the error.
4. Never retry a **403**, which is an authorization decision. Retry a **429** only after `Retry-After`, and never auto-retry a failed login.
5. Base URLs come from the environment, and anything other than localhost must use `https://`.
