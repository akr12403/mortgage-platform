# mortgage-api-consumer (M6 Task 6.4)

A small TypeScript client that calls the platform the secure way. It logs in for a JWT, keeps the token **in memory only**, sends it as `Authorization: Bearer …` to mortgage-service and servicing-service, and **logs in again automatically** when the token expires or is rejected.

It has no runtime dependencies: it uses Node 22's built-in `fetch`. `typescript` and `@types/node` are dev-only.

```text
clients/mortgage-api-consumer/
├── src/
│   ├── auth.ts            # AuthSession: login, in-memory token, proactive + reactive re-login (single-flight)
│   ├── http.ts            # AuthenticatedTransport: Bearer + X-Correlation-Id, 401 → re-login once, 429 → Retry-After
│   ├── mortgageClient.ts  # getMortgage, getServicingHistory, createMortgage + createMortgageApiConsumer()
│   ├── config.ts          # env-only configuration, HTTPS enforcement for non-local hosts
│   ├── errors.ts          # ApiError (status, code, correlationId), ConfigError
│   └── index.ts           # npm run demo
├── test/client.test.ts    # node:test suite against a scripted fake server (no stack needed)
├── .env.example           # variable names only, no values
├── package.json
└── tsconfig.json
```

## Run

You need the compose stack running (`docker compose up --build -d` from the repo root) and Node 22+.

```bash
cd clients/mortgage-api-consumer
npm install                      # creates package-lock.json: commit it
export MORTGAGE_API_BASE=http://localhost:8080
export SERVICING_API_BASE=http://localhost:8081
export MORTGAGE_API_PASSWORD="$(grep '^AUTH_SEED_PASSWORD=' ../../.env | cut -d= -f2-)"   # local seed password
npm test                         # unit tests, no stack needed
npm run demo
```

Windows PowerShell: `$env:MORTGAGE_API_BASE="http://localhost:8080"`, and set `$env:MORTGAGE_API_PASSWORD` the same way.

**No Node on your machine?** Run it in a container. Inside a container, `localhost` is the container itself, so point it at `host.docker.internal`:

```bash
cd clients/mortgage-api-consumer
docker run --rm -v "$PWD":/app -w /app \
  -e MORTGAGE_API_BASE=http://host.docker.internal:8080 \
  -e SERVICING_API_BASE=http://host.docker.internal:8081 \
  -e MORTGAGE_API_PASSWORD="$(grep '^AUTH_SEED_PASSWORD=' ../../.env | cut -d= -f2-)" \
  node:22-alpine sh -c "npm install && npm test && npm run demo"
```

### Configuration (environment only)

| Variable | Default | Notes |
| --- | --- | --- |
| `MORTGAGE_API_BASE` | `http://localhost:8080` | mortgage-service; also the token issuer |
| `SERVICING_API_BASE` | `http://localhost:8081` | servicing-service |
| `MORTGAGE_API_USERNAME` | `servicing@capstone.local` | any seed user; try `support@` or `underwriter@` |
| `MORTGAGE_API_PASSWORD` | falls back to `AUTH_SEED_PASSWORD` | **required**; never commit it |
| `MORTGAGE_API_TIMEOUT_MS` | `10000` | per-request timeout |
| `ALLOW_INSECURE_HTTP` | `false` | plain HTTP is accepted only for `localhost`, `127.0.0.1`, `[::1]` and `host.docker.internal`; anything else must be `https://` unless this is `true` |
| `DEMO_MORTGAGE_ID` | `MTG-1001` | mortgage used by the demo |

## Demo flow

| Step | What happens | Shows |
| --- | --- | --- |
| 1 | `POST /api/v1/auth/login` as `servicing@` | the token is held in memory; only roles and expiry are printed |
| 2 | `GET :8080/api/v1/mortgages/MTG-1001` | Bearer header on a protected call |
| 3 | `GET :8081/api/v1/mortgages/MTG-1001/servicing-history` | the same token is accepted by a second service |
| 4 | the in-memory token is tampered with, then step 2 is repeated | the server answers a **real 401 `INVALID_TOKEN`**; the client logs in again and the retry succeeds |
| 5 | `POST /api/v1/mortgages` with the same identity | **403 `ACCESS_DENIED`** is surfaced, not retried: RBAC is enforced by the server (skipped automatically for ADMIN and UNDERWRITER, who are allowed) |

Step 4 tampers with the token so the demo can show the expiry path without waiting for `JWT_TTL_SECONDS` (1 hour). The client code path is the same one a genuinely expired token takes.

## Token handling rules

- **Renewal = re-login.** The platform issues short-lived access tokens without refresh tokens (`docs/security/authentication.md`).
  - **Proactive:** the client logs in again when the token is within 30 s of expiring, so calls never race the deadline.
  - **Reactive:** on a 401 the client drops that token, logs in **once** and retries **once**. A second 401 is returned to the caller; it never loops.
  - **Single-flight:** concurrent requests that all get 401 share one login request.
- **403 is final.** A permission problem isn't fixed by re-authenticating. The client never retries a 403 and never assumes roles on its own: the server is the authority. Hiding UI buttons by role is fine, but trusting it is not.
- **429** is retried after `Retry-After`, at most twice, waiting no more than 10 s each time. A failed login is **never** auto-retried, because brute-force protection on the server rate-limits logins.
- **Storage.** No token or password is written to disk, put in a URL, or logged. `JSON.stringify(session)` and `console.log(session)` show only `{authenticated, roles, expiresInMs}`. `ApiError` carries `status`, `code`, `message` and `correlationId`, never headers.
- **Transport.** Every call gets an `X-Correlation-Id` (it shows up in the service logs), a timeout and `Accept: application/json`. Path IDs are validated (`MTG-####`) and URL-encoded before sending; the server still validates everything.

## Use as a library

```ts
import { loadConfig } from "./config.js";
import { createMortgageApiConsumer } from "./mortgageClient.js";

const { client, session } = createMortgageApiConsumer(loadConfig());
const mortgage = await client.getMortgage("MTG-1001");
const history = await client.getServicingHistory("MTG-1001");
session.clear(); // logout: forget the token
```
