# Test Strategy (M10 Task 10.1)

How the platform is tested, where each kind of test lives, what it proves, and which pipeline gate runs it. The goal is the milestone's: show the platform is release-ready, with every critical user journey automated end to end.

## Test pyramid

| Layer | Where | Count | Runs in | What it proves |
| --- | --- | --- | --- | --- |
| **Unit** (colocated with each service) | `services/*/src/test`, `analytics/mortgage-analytics-service/tests`, `ai/mortgage-knowledge-assistant/tests`, `clients/mortgage-api-consumer/test`, `infrastructure/{glue,aws/lambda/doc_processor}/tests` | Java 77 + 28, analytics 80, assistant 119, TS client 16, ETL/Lambda | `unit-tests` (one matrix job per suite) | Business rules (payments, delinquency bands, approval workflow), retrieval, redaction, guardrails, the event publisher, the token-handling client |
| **API** (HTTP contract of each service, in-process) | Java `controller/*ApiTest`, `InputValidationTest`, `security/*Test` (MockMvc); analytics and assistant `test_api.py` (FastAPI TestClient) | part of the unit counts | `unit-tests` | Status codes, the error envelope, validation, role checks per route, idempotency, 503 on database loss |
| **Contract** | `tests/contract` (event schemas ↔ examples ↔ catalog ↔ producers; Splunk assets ↔ runbook), Java `EventSchemaContractTest` | 14 + 1 | `unit-tests` (`repo-checks`) | Producers and consumers agree on every event; every alert has a runbook section |
| **Security** | `tests/security`: `test_auth_smoke`, `test_rbac_smoke` (all 5 roles), `test_owasp_smoke` against the running stack; `test_static_sql`, `test_iam_policies` as static guards | 19 live + 13 static | `integration-tests`; static ones in `unit-tests` | Authentication, the full RBAC matrix, OWASP API Top 10 regressions from M6, no string-built SQL, least-privilege IAM |
| **Integration** | `tests/integration/test_stack_smoke.py` | 2 | `integration-tests` | All 4 services healthy on the pipeline's own images; one payment travels SNS → SQS to both consumers exactly once |
| **E2E** | `tests/e2e` (Cucumber features + Playwright API requests) | 5 journeys, 16 scenarios | `e2e-tests` | The five business journeys below, across services and events, as a user would run them |
| **Infrastructure** | `tests/infrastructure/test_terraform_layout.py`, `terraform fmt`/`validate` (`infra.yml`), the drift check | | `unit-tests`, `infra` | Modules and environments stay identical except for `tfvars`; drift is detected |
| **Non-functional** | Performance smoke (M10 Task 10.4), the incident drill (`scripts/incident/db_outage_drill.py`) | | manual, recorded | Baseline latency; detection and recovery from a database outage ([RCA](rca-2026-11-10.md)) |

The handbook's `tests/{unit,api,integration,security,e2e}` layout is followed where tests run against the whole stack (`tests/security`, `tests/integration`, `tests/e2e`). Unit and in-process API tests stay next to the code they test, which the handbook allows ("or colocated in services"), so each service builds and tests on its own. `tests/api` is kept empty for that reason; its role is covered by the API tests listed above.

## E2E journeys (M10 Task 10.3)

Each journey is a Cucumber feature tagged with its journey and its M2 user stories, so `npm test -- --tags @US-PAY-001` runs everything that covers a story.

| Journey | Feature | Stories | What the scenarios check |
| --- | --- | --- | --- |
| J1 Onboarding | `j1_onboarding.feature` | US-BOR-001, US-MTG-001 | Create borrower (201) → create mortgage with a pending loan (PENDING) → underwriting decision APPROVED (ACTIVE) → servicing-service has MORTGAGE_CREATED and LOAN_APPROVED. A duplicate borrower ID → 409. |
| J2 Payment → history | `j2_payment_history.feature` | US-PAY-001, US-SRV-001 | Payment posted → balance lowered by the amount → listed → PAYMENT_POSTED in the servicing history. Same Idempotency-Key twice → replayed, balance lowered once, one history entry. |
| J3 Delinquency | `j3_delinquency.feature` | US-DEL-001 | Seeded MTG-1002 is DELINQUENT (≥ 30 days, severity). A failed installment 45 days past due → mortgage DELINQUENT → snapshot MODERATE → PAYMENT_MISSED and DELINQUENCY_ASSIGNED in the history. |
| J4 Access denied | `j4_authorization.feature` | US-SEC-001, US-SEC-002 | Support can't approve a loan (403 ACCESS_DENIED, mortgage unchanged); 4 more role denials; no token → 401 UNAUTHORIZED; tampered token → 401 INVALID_TOKEN; the assistant requires a token. |
| J5 RAG | `j5_assistant.feature` | US-AI-001 | A policy question → answer with ≥ 1 citation, each a real knowledge-base chunk of the cited document. An off-topic question → no citations, confidence below the threshold. |

**Coverage targets.** Critical paths: 100% E2E, meaning each of the seven M2 stories the handbook maps to J1–J5 (table above) has a passing scenario. Every role-restricted route: a denial test (`RbacMatrixTest` in both Java services and `test_rbac_smoke`). Every event type: a contract test. Line coverage isn't measured; adding JaCoCo and `pytest-cov` reports is listed as a known limitation in the readiness review.

## How the E2E suite is built (M10 Task 10.2)

- **Approach.** The platform has no UI, so the journeys are API-level, as the handbook allows: Cucumber (`@cucumber/cucumber`) runs the Gherkin features, and the steps call the services through Playwright's `APIRequestContext` (`playwright-core`, no browser).
- **API objects instead of page objects.** `tests/e2e/api/apis.mjs` has one class per service (`AuthApi`, `BorrowerApi`, `MortgageApi`, `ServicingApi`, `AssistantApi`) that owns its routes and request shapes; steps never build URLs.
- **Independent scenarios.** Each scenario creates its own borrower and mortgage (fresh business IDs, retried on 409), so scenarios run in parallel (`parallel: 2`) and can be re-run against the same database. Only J4's denials touch seed data, and they change nothing.
- **Asynchronous checks.** Steps that depend on an event poll for up to 60 s (`E2E_EVENT_TIMEOUT_MS`), like the integration test.
- **Flakiness.** `retry: 1`; a scenario that passes on retry is reported as flaky rather than hidden.
- **Traceability.** Each scenario sends its own `X-Correlation-Id: e2e-<uuid>`, attached to the report, so a failure can be followed in Splunk with `index=mortgage_dev correlationId="e2e-…"`.
- **Reports.** `reports/e2e/cucumber-report.html` (uploaded as the `e2e-report` artifact) and `reports/junit/e2e-cucumber.xml` (the job summary).

## Test environments and data

| Where | Stack | Data | J5 assistant |
| --- | --- | --- | --- |
| Pipeline `e2e-tests` | Compose stack from the scanned `sha-<commit>` images (`scripts/ci/e2e-tests.sh`) | Fresh database with the seed data, throwaway secrets | Offline embedder and an LLM stub over HTTPS ([`docker-compose.e2e.yml`](../../tests/e2e/docker-compose.e2e.yml)): the assistant's retrieval, gate, citation check and contract run unchanged, the model is replaced |
| Local | Your running stack (`docker compose up -d`) | Seed data plus earlier runs' borrowers and mortgages (harmless: fresh IDs each run) | Your real LLM (`LLM_API_KEY` in `.env`), after `docker compose run --rm knowledge-ingest` |

No production or real borrower data is used anywhere: the seed data is synthetic, and the E2E borrowers are named `E2E Borrower<n>` with `@example.test` addresses.

**What the pipeline's J5 does and doesn't prove.** It proves the assistant's own controls: no answer without a retrieved passage, citations limited to the passages actually retrieved, and the response contract. It doesn't prove answer quality, which depends on the real model. That's covered by the M7 evaluation set ([docs/ai](../ai/)) and by running J5 locally against the real model before a release.

## Pipeline gates

```text
unit-tests (6 suites) ──┐
security gates ─────────┴─> container-build -> container-scan ─┬─> integration-tests ─┬─> publish -> deploy-dev
                                                              └─> e2e-tests ─────────┘
```

A failure in any of them stops the images from being published, so nothing untested reaches `:develop`, `:main` or dev. The E2E job runs on every pull request and push, in parallel with the integration tests; it takes about the same time (stack start-up dominates).

## Running the tests

```bash
# E2E against your running stack (seed password from .env)
cd tests/e2e && npm ci && npm test
npm test -- --tags @J3                    # one journey
npm test -- --tags "not @J5"              # without the assistant

# Other suites
bash scripts/ci/unit-tests.sh <suite>      # mortgage-service | servicing-service | analytics-service | knowledge-assistant | ts-client | repo-checks
LOCAL_IMAGES=1 bash scripts/ci/integration-tests.sh
```
