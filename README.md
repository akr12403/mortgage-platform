# Mortgage Intelligence & Servicing Platform

The Enterprise Mortgage Platform is an event-driven, microservices-based system designed to streamline the entire mortgage loan lifecycle—from initial borrower application and automated underwriting to servicing, payment processing, delinquency workflows, portfolio risk analytics, and AI-assisted document intelligence. Engineered with security, auditability, and scalability at its core, the platform integrates Java/Spring microservices, Python data analytics, event streaming, and cloud-native infrastructure.

---

## Master Progress Tracker

| ID | Milestone | Week | Doc | Status |
| --- | --- | --- | --- | --- |
| **M1** | Foundation & Architecture | 1 | `docs/milestones/m01.md` | **Completed** |
| **M2** | Agile & Data Foundation | 2 | `docs/milestones/m02.md` | **Completed** |
| **M3** | Python Analytics | 3 | `docs/milestones/m03.md` | **Completed** |
| **M4** | Java / Spring Backend | 4–5 | `docs/milestones/m04.md` | **Completed** |
| **M5** | Microservices & Events | 6 | `docs/milestones/m05.md` | **Completed** |
| **M6** | Security Engineering | 7–8 | `docs/milestones/m06.md` | **Completed** |
| **M7** | AI / RAG Assistant | 9 | `docs/milestones/m07.md` | **Completed** |
| **M8** | AWS & Data Platform | 10 | `docs/milestones/m08.md` | In progress |
| **M9** | CI/CD, Terraform, Observability | 11 | `docs/milestones/m09.md` | Planned |
| **M10** | Testing & Production Readiness | 12 | `docs/milestones/m10.md` | Planned |

---

## Milestone 1 Artifacts & Index

All foundational requirements and baseline architecture documentation created during Milestone 1 are linked below for rapid review:

### Requirements & Scope
- **Project Charter**: [docs/requirements/team-charter.md](docs/requirements/team-charter.md)
- **Project Scope**: [docs/requirements/project-scope.md](docs/requirements/project-scope.md)
- **Stakeholder Map**: [docs/requirements/stakeholder-map.md](docs/requirements/stakeholder-map.md)
- **User Personas**: [docs/requirements/personas.md](docs/requirements/personas.md)
- **Business Flow (Mortgage Lifecycle)**: [docs/requirements/business-flow.md](docs/requirements/business-flow.md)
- **Backlog & Epics**: [docs/requirements/backlog-epics.md](docs/requirements/backlog-epics.md)
- **Engineering Standards**: [docs/requirements/engineering-standards.md](docs/requirements/engineering-standards.md)

### Baseline Architecture & Topology
- **System Context (C4 Level 1)**: [docs/architecture/system-context.md](docs/architecture/system-context.md)
- **Application Architecture**: [docs/architecture/application-architecture.md](docs/architecture/application-architecture.md)
- **Deployment Architecture & Topology**: [docs/architecture/deployment-architecture.md](docs/architecture/deployment-architecture.md)
- **Data Flow (Document Upload Trace)**: [docs/architecture/data-flow.md](docs/architecture/data-flow.md)
- **Trust Boundaries & Security Controls**: [docs/architecture/trust-boundaries.md](docs/architecture/trust-boundaries.md)

---

## 🚀 Milestone 2 Status: COMPLETED
Milestone 2 establishes the core database foundation, synthetic data seeding, operational query workflows, and DevSecOps baseline guardrails.

### Summary of Completed Components
- **Database Architecture & Migrations (`/database`)**: 
  - Full relational schema covering 7 core entities (Borrowers, Mortgages, Loans, Payments, Delinquencies, Servicing History, and Document Metadata) utilizing PostgreSQL and `pgcrypto`.
  - Automated local development reset and seed utility (`reset-dev-db.ps1`).
- **Synthetic Data & Seeding (`database/seed/`)**: 
  - Faker-compliant synthetic datasets containing representative borrower profiles, active loans, and delinquency cases (`MTG-1001`, `MTG-1002`, `MTG-1005`).
- **Operational Queries & Lab Artifacts (`database/scripts/`)**: 
  - Borrower-to-loan joins, outstanding balance aggregations, and delinquency reporting views.
  - Performance documentation (`docs/architecture/query-notes.md`) featuring index optimization on `servicing_history(event_time)` to eliminate sequential scan overhead.
- **DevSecOps Baseline (`docs/operations/devsecops-baseline.md`)**: 
  - GitHub branch protection rules enforced on `main` and `develop` (requiring pull requests, approvals, and status checks).
  - Minimum CI pipeline stub (`.gitlab-ci.yml`) for validation and secret scanning hooks.
  - Standardized code review checklists and PR templates.

---

## 🚀 Milestone 3 Status: COMPLETED
Milestone 3 implements the Python-based data analytics and portfolio processing pipelines for aggregation, compliance reporting, and automation support.

### Summary of Completed Components
- **Data Processing & Analytics Scripts**: 
  - Python scripts utilizing optimized data structures (`defaultdict`, pandas) to parse campaign data, aggregate metrics, and compute access review durations.
- **Financial & Portfolio Simulation Tools**: 
  - Automated data utilities for processing loan metrics, validation datasets, and analytics support across backend services.

---

## 🚀 Milestone 4 Status: COMPLETED
Milestone 4 delivers the core Java / Spring Boot microservices backend (`mortgage-service` and `servicing-service`), full REST API implementation, JPA persistence, transaction management, structured logging, and automated test coverage.

### Summary of Completed Components
- **Microservices Architecture (`mortgage-service` & `servicing-service`)**: 
  - Multi-service Spring Boot application topology running locally on ports `8080` and `8081`.
- **Domain Model & JPA Entities**: 
  - Fully implemented relational JPA entities (`Borrower`, `Mortgage`, `Payment`, `ServicingHistory`) with constraint validation (`@Valid`, `@NotNull`, `@NotBlank`, `@DecimalMin`).
- **RESTful Endpoints & Business Logic**: 
  - Borrower registration (`/api/v1/borrowers`), mortgage creation and pagination (`/api/v1/mortgages`), atomic payment processing with automatic balance updates (`/api/v1/mortgages/{id}/payments`), servicing history tracking, and risk/delinquency evaluation (`/api/v1/mortgages/{id}/delinquency`).
- **Observability & Traceability**: 
  - Structured request logging with custom correlation ID (`X-Correlation-Id`) tracking across system components.
  - Actuator health and readiness endpoint configuration.
- **Automated Testing & Quality Assurance**: 
  - Comprehensive unit and integration test suites (`mvn test`) passing successfully across controllers, services, and database layers.

---

## 🚀 Milestone 5 Status: COMPLETED — MICROSERVICES, EVENTS & CONTAINERS

M5 turns the repo into a documented, event-driven microservice architecture: contract-first APIs, lifecycle events over **SNS → SQS → consumers** with retries and DLQs, and three containerized services with health checks.

| Area | Where |
| --- | --- |
| Architecture overview (start here) | [docs/architecture/microservice-architecture.md](docs/architecture/microservice-architecture.md) |
| Boundaries, ownership, ADR | [application-architecture.md](docs/architecture/application-architecture.md), [service-ownership-matrix.md](docs/architecture/service-ownership-matrix.md), [ADR-002](docs/adr/ADR-002-microservices-decomposition.md) |
| API contracts (v1) | [mortgage-service](docs/api/mortgage-service-openapi.yaml), [servicing-service](docs/api/servicing-service-openapi.yaml), [analytics](docs/api/mortgage-analytics-service-openapi.yaml), [Postman](docs/api/postman/mortgage-platform-m5.postman_collection.json) |
| Events | [event-catalog.md](docs/architecture/event-catalog.md), JSON Schemas in [docs/architecture/events/](docs/architecture/events/) |
| Messaging operations | [messaging-runbook.md](docs/operations/messaging-runbook.md) |
| Demo & sign-off | [m5-demo-checklist.md](docs/operations/m5-demo-checklist.md), `bash scripts/m5-demo.sh` |

### Verification evidence (local Docker stack, 2026-10-20)

| Check | Result |
| --- | --- |
| `mortgage-service` tests (`mvn -B test`) | 41 passed, 0 skipped (includes `EventSchemaContractTest`) |
| `servicing-service` tests (`mvn -B test`) | 13 passed |
| Repository contract checks (`tests/contract`) | 20 passed: schemas ↔ examples ↔ catalog ↔ Java producer payloads ↔ OpenAPI |
| `docker compose up --build -d` | postgres, localstack, mortgage-service, servicing-service, analytics-service **healthy** (Dockerfile `HEALTHCHECK`); `db-migrate`, `messaging-init` exited 0 |
| `bash scripts/m5-demo.sh` | `MortgageCreated` → `LoanApproved` → `PaymentReceived` (idempotent replay, no duplicate) → `PaymentMissed` + `LoanDelinquent` consumed into servicing history and delinquency snapshot; one correlation ID traced HTTP → producer logs → consumer logs; poison event retried 3× (ERROR logged) then moved to `capstone-mortgage-servicing-dlq-dev` at ~90 s |
| Error envelope | unknown mortgage → 404 `MORTGAGE_NOT_FOUND` with `correlationId` + `timestamp` |

All M5 Definition of Done items and their evidence: [docs/operations/m5-demo-checklist.md](docs/operations/m5-demo-checklist.md).

### Run the stack

```bash
cp .env.example .env            # REQUIRED since M6: set JWT_SECRET (openssl rand -base64 48) and AUTH_SEED_PASSWORD
docker compose up --build -d
docker compose ps               # postgres, localstack, mortgage-service, servicing-service, analytics-service, knowledge-assistant -> healthy
curl localhost:8080/actuator/health; curl localhost:8081/actuator/health; curl localhost:8000/health
bash scripts/m5-demo.sh         # end-to-end demo incl. DLQ (logs in with AUTH_SEED_PASSWORD from .env)
docker compose run --rm knowledge-ingest   # M7: load the knowledge base into pgvector (needs LLM_API_KEY in .env)
curl localhost:8001/health/ready           # M7: knowledgeChunks 51, aiProviderConfigured true
bash scripts/m7-demo.sh                    # M7: grounded Q&A, insufficient context, prompt library, incident summary
```

Do **not** use `docker compose down -v` unless you intend to wipe the database volume (it re-seeds on next start).

> ⚠️ **Local plain HTTP only.** The compose stack serves HTTP on `localhost` (8080, 8081, 8000, 8001) with **synthetic data**, for local development only. Any shared or deployed environment must use **HTTPS**: TLS terminates at the load balancer and is re-encrypted to the services ([encryption in transit](docs/security/security-controls.md#in-transit)). Never point a local stack at real borrower data. The TypeScript client refuses plain HTTP to any non-local host.

### Testing

```bash
# Java (mount the repo root so the event-schema contract test can read docs/)
for s in mortgage-service servicing-service; do
  docker run --rm -v "$PWD":/workspace -v "$HOME/.m2":/root/.m2 -w /workspace/services/$s \
    maven:3.9-eclipse-temurin-17 mvn -B test
done

# Python analytics (dedicated test stage; runtime image carries no test tooling)
docker build -f docker/Dockerfile.analytics-service --target test -t capstone/analytics-tests .
docker run --rm capstone/analytics-tests

# M6 auth + RBAC + OWASP smoke tests against the running stack (stdlib only)
python3 tests/security/test_auth_smoke.py
python3 tests/security/test_rbac_smoke.py
python3 tests/security/test_owasp_smoke.py

# M6 static check: no string-built SQL anywhere (no stack needed)
python3 tests/security/test_static_sql.py

# M6 CI security gates (same as GitHub Actions / GitLab): secrets, SAST, dependency scanning. Needs Docker.
sh scripts/security-gates.sh all

# M6 TypeScript secure API consumer (Node 22+; see clients/mortgage-api-consumer/README.md for the Docker variant)
(cd clients/mortgage-api-consumer && npm install && npm test && \
  MORTGAGE_API_PASSWORD="$(grep '^AUTH_SEED_PASSWORD=' ../../.env | cut -d= -f2-)" npm run demo)

# M7 knowledge assistant (fake embedder + scripted LLM: no API key, network or database needed)
docker build -f docker/Dockerfile.knowledge-assistant --target test -t ka-test . && docker run --rm ka-test
docker run --rm -v "$PWD":/repo -w /repo/ai/mortgage-knowledge-assistant ka-test \
  python -m pytest -q -p no:cacheprovider tests/test_prompt_library.py tests/test_incident.py   # docs/runbook link checks

# Repository contract checks (schemas <-> examples <-> catalog <-> Java producer records)
docker run --rm -v "$PWD":/w -w /w python:3.14.7-slim sh -c "pip install -q pytest jsonschema && python -m pytest -q tests/contract"
```

---

## 🚀 Milestone 6 Status: COMPLETED — SECURITY ENGINEERING

M6 secures the platform end to end:

- **authentication:** JWT login;
- **authorization:** RBAC for five roles, with server-side enforcement and deny by default;
- **OWASP API Top 10 hardening;**
- **a secure TypeScript API consumer;**
- **data protection:** classification, encryption and secrets rotation;
- **security testing artifacts;**
- **blocking CI security gates.**

| Area | Where |
| --- | --- |
| Authentication (6.1) | [docs/security/authentication.md](docs/security/authentication.md) |
| RBAC matrix (6.2), OWASP controls (6.3), data classification + encryption (6.5) | [docs/security/security-controls.md](docs/security/security-controls.md) |
| TypeScript secure API consumer (6.4) | [clients/mortgage-api-consumer/](clients/mortgage-api-consumer/README.md) |
| Secrets rotation runbook (6.5) | [docs/operations/runbook.md](docs/operations/runbook.md#secrets-rotation) |
| STRIDE threat model, risk register, vulnerability report, remediation backlog (6.6) | [threat-model.md](docs/security/threat-model.md), [risk-register.md](docs/security/risk-register.md), [vulnerability-report.md](docs/security/vulnerability-report.md), [remediation-backlog.md](docs/security/remediation-backlog.md) |
| Secure CI gates (6.7) | [docs/operations/devsecops-baseline.md](docs/operations/devsecops-baseline.md), `scripts/security-gates.sh`, `.github/workflows/security-gates.yml`, `.gitlab-ci.yml` |
| Demo & sign-off (validation + Definition of Done → evidence) | [docs/operations/m6-demo-checklist.md](docs/operations/m6-demo-checklist.md), `bash scripts/m6-demo.sh` |

### Verification evidence (2026-10-24)

| Check | Result |
| --- | --- |
| `mortgage-service` / `servicing-service` tests | **131 / 37 passed** (Spring Boot 3.5.16 with patched Tomcat, Netty, Jackson and pgjdbc) |
| Analytics tests | **82 passed** |
| TypeScript client tests + demo against the live stack | **16/16**; login → GET mortgage → GET servicing history → 401 → re-login + retry → 403 surfaced |
| Live smoke tests (auth / RBAC / OWASP) | **7/7 · 4/4 · 8/8** |
| Security gates (`sh scripts/security-gates.sh all`, and GitHub Actions on PR #90) | secrets: no leaks in history; SAST: 0 findings; dependencies: 0 High/Critical; Python: no known vulnerabilities |
| Intentional test secret (PR #91) | `secret-detection` **failed after 8 s**; PR closed without merging ([evidence](docs/operations/devsecops-baseline.md#pipeline-evidence-redacted-screenshot)) |
| Vulnerabilities | 19 findings: **0 Critical/High open**; 2 Low open and 4 accepted with owner and expiry ([report](docs/security/vulnerability-report.md)) |
| SUPPORT cannot approve a loan (M10 Journey 4) | 403 `ACCESS_DENIED` (`RbacMatrixTest`, `test_rbac_smoke.py`) |

**Known limits (stated, not hidden):**

- GitHub branch protection is configured but **not enforced** on this free private repository. The gates still run and fail visibly, and enforcement needs an organization plan (M9).
- Two Spring Framework 6.2 CVEs with no open-source fix on the 3.5 line are **accepted until 2026-12-31** (unreachable, vendor-rated Medium/Low). The Spring Boot 4 migration is planned for M9 (B-18).
- The peer and instructor review boxes in the threat model and risk register are completed at the M6 review session.

---

## 🚀 Milestone 7 Status: COMPLETED — AI/RAG MORTGAGE ASSISTANT

M7 adds a **mortgage knowledge assistant** (`ai/mortgage-knowledge-assistant/`, port 8001) that answers staff policy questions only from a controlled, versioned knowledge base, with citations:

- **RAG pipeline:** 5 synthetic policy documents → section-aware chunks (≤ 512 tokens) → `text-embedding-3-small` → **pgvector** → top-5 retrieval with a calibrated similarity gate → `gpt-6-luna` with a context-only prompt and strict JSON → citations verified in code;
- **insufficient context** instead of guessing (the LLM is not called for off-corpus questions);
- **API:** `POST /api/v1/assistant/ask` behind the M6 JWT, rate limited, correlation IDs, audit log without question text;
- **prompt library** (6 versioned templates) and **AI governance** (human-approval scenarios, logging and PII rules, tested hallucination controls);
- **incident summarization** (Session 27) with runbook links from a fixed catalogue and a code-decided `requiresHumanApproval` flag.

| Area | Where |
| --- | --- |
| Knowledge base v1 (7.1) | [ai/mortgage-knowledge-assistant/knowledge/](ai/mortgage-knowledge-assistant/knowledge/README.md) |
| Ingestion, retrieval, generation, API, incidents (7.2–7.4, 7.6) | [service README](ai/mortgage-knowledge-assistant/README.md), [OpenAPI](docs/api/mortgage-knowledge-assistant-openapi.yaml), migration `database/migrations/005_knowledge_chunk.sql` |
| Prompt library and governance (7.5) | [docs/ai/prompt-library.md](docs/ai/prompt-library.md), [docs/ai/governance.md](docs/ai/governance.md) |
| Security review of the assistant | threats T-26–T-32 in [threat-model.md](docs/security/threat-model.md), risks R-18–R-20 in [risk-register.md](docs/security/risk-register.md), RBAC and rate limits in [security-controls.md](docs/security/security-controls.md) |
| Demo & sign-off (validation + Definition of Done → evidence) | [docs/operations/m7-demo-checklist.md](docs/operations/m7-demo-checklist.md), `bash scripts/m7-demo.sh` |

### Verification evidence (2026-10-24/25)

| Check | Result |
| --- | --- |
| Assistant tests (Docker test image) | **172 passed**, plus the 4 docs/runbook-link checks passing with the repo mounted |
| Ingestion | 5 documents → **51 chunks** (largest 301 tokens); re-run embeds 0 |
| Threshold calibration | hit@5 **11/11**; on-corpus best 0.528–0.768 vs off-corpus 0.065–0.374 → threshold **0.45** (handbook 0.7 answered only 3/11) |
| Grounded answer over HTTP | "What is the delinquency contact timeline?" → cites `delinquency-playbook:v1:c-05`, confidence 0.76 |
| Insufficient context | "What is the capital of France?" → best 0.073, no citation, LLM not called |
| Human approval | "Should we start foreclosure on MTG-1002…?" → answered with citation, `requiresHumanApproval: true` |
| Incident summaries | `INC-2026-0042` → SEV2, cause found, `messaging-dlq`, confidence 0.98, no flag · `INC-2026-0043` → UNKNOWN, 0.25–0.30, **flagged** |
| Security gates on every M7 PR (#94–#99) | secrets: no leaks; SAST: 0 findings; dependencies: no known vulnerabilities |

**Known limits (stated, not hidden):**

- The handbook's `gpt-4o-mini` is deprecated (shutdown 2027-01-14); the assistant uses `gpt-6-luna`, set by `LLM_MODEL`.
- Approval rules are keyword-based, and pattern redaction cannot detect names or addresses; both are recorded as residual risks R-18 and R-19.
- Rate limits are in-memory per container, as for the other services (shared throttling in M9).
- The peer or instructor review box in the M7 checklist is completed at the M7 review session.

---

## 🛠️ Local Development & Reset Workflow
To reset and seed your local PostgreSQL environment:
```powershell
.\database\scripts\reset-dev-db.ps1