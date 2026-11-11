# E2E journeys (M10)

The platform's five critical user journeys as Cucumber features, run against the live services. There is no UI, so the steps call the APIs through Playwright's API request context (`playwright-core`, no browser), as the M10 handbook allows. Strategy, coverage and pipeline gate: [docs/operations/test-strategy.md](../../docs/operations/test-strategy.md).

| Journey | Feature | Stories |
| --- | --- | --- |
| J1 Borrower → mortgage onboarding (with the underwriting decision) | [j1_onboarding.feature](features/j1_onboarding.feature) | US-BOR-001, US-MTG-001 |
| J2 Payment → servicing history | [j2_payment_history.feature](features/j2_payment_history.feature) | US-PAY-001, US-SRV-001 |
| J3 Missed payment → delinquency | [j3_delinquency.feature](features/j3_delinquency.feature) | US-DEL-001 |
| J4 Unauthorized → denied (401/403) | [j4_authorization.feature](features/j4_authorization.feature) | US-SEC-001, US-SEC-002 |
| J5 Question → grounded answer with citations | [j5_assistant.feature](features/j5_assistant.feature) | US-AI-001 |

## Run locally

Prerequisites: Node 22+, the stack running (`docker compose up -d`), and `AUTH_SEED_PASSWORD` in the repo-root `.env` (read from there; never put it in this folder). For J5, the assistant must be ready: `LLM_API_KEY` in `.env` and the knowledge base ingested (`docker compose run --rm knowledge-ingest`).

```bash
cd tests/e2e
npm ci                                   # first time (npm install if there's no package-lock.json yet)
npm test                                 # all journeys, 2 in parallel, 1 retry
npm test -- --tags @J2                   # one journey
npm test -- --tags @US-DEL-001           # everything covering a user story
npm test -- --tags "not @J5"             # skip the assistant (no LLM key)
npm run dry-run                          # check every step has a definition, without calling anything
```

Results: a summary in the terminal, the HTML report at `reports/e2e/cucumber-report.html` and JUnit at `reports/junit/e2e-cucumber.xml` (repo root, git-ignored).

Settings (environment variables): `MORTGAGE_API_BASE`, `SERVICING_API_BASE`, `ASSISTANT_API_BASE` (default `http://localhost:8080`, `:8081`, `:8001`), `E2E_PARALLEL` (2), `E2E_RETRY` (1), `E2E_EVENT_TIMEOUT_MS` (60000), `RAG_SIMILARITY_THRESHOLD` (0.45).

## In the pipeline

The `e2e-tests` job (`scripts/ci/e2e-tests.sh`) starts the stack from the scanned images, with [docker-compose.e2e.yml](docker-compose.e2e.yml) on top: the assistant uses the offline embedder and [an LLM stub](llm-stub/llm_stub.py) over HTTPS, so J5 runs without an API key. The assistant's own code runs unchanged (retrieval, similarity gate, citation check, response contract); only the model is replaced. The job uploads the HTML report as the `e2e-report` artifact, and `publish` waits for it.

## Layout

```text
features/        one .feature per journey, tagged @J<n> and with its user stories
steps/           step definitions, grouped by area (common, onboarding, payments, delinquency, security, assistant)
api/             API objects: one class per service owning its routes and request shapes (http.mjs wraps Playwright)
support/         configuration, test data (fresh business IDs per scenario), the World and hooks
llm-stub/        OpenAI-compatible stub and its throwaway TLS, pipeline only
cucumber.mjs     paths, reports, parallelism, retry
```

**Writing a scenario.** Reuse steps from `steps/common.steps.mjs` where you can (`I am logged in as …`, `the response status should be …`, `the servicing history eventually shows …`). Create the data the scenario needs (`an active mortgage created for this scenario`) instead of depending on another scenario or on seed data that other tests change. Each scenario's `correlationId` is in the report: search it in Splunk to see what every service logged for it.
