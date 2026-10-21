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
| **M5** | Microservices & Events | 6 | `docs/milestones/m05.md` | In review (`feature/M5-task5-fix`) |
| **M6** | Security Engineering | 7–8 | `docs/milestones/m06.md` | Planned |
| **M7** | AI / RAG Assistant | 9 | `docs/milestones/m07.md` | Planned |
| **M8** | AWS & Data Platform | 10 | `docs/milestones/m08.md` | Planned |
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

## 🚀 Milestone 5 Status: MICROSERVICES, EVENTS & CONTAINERS

M5 turns the repo into a documented, event-driven microservice architecture: contract-first APIs, lifecycle events over **SNS → SQS → consumers** with retries and DLQs, and three containerized services with health checks.

| Area | Where |
| --- | --- |
| Architecture overview (start here) | [docs/architecture/microservice-architecture.md](docs/architecture/microservice-architecture.md) |
| Boundaries, ownership, ADR | [application-architecture.md](docs/architecture/application-architecture.md), [service-ownership-matrix.md](docs/architecture/service-ownership-matrix.md), [ADR-002](docs/adr/ADR-002-microservices-decomposition.md) |
| API contracts (v1) | [mortgage-service](docs/api/mortgage-service-openapi.yaml), [servicing-service](docs/api/servicing-service-openapi.yaml), [analytics](docs/api/mortgage-analytics-service-openapi.yaml), [Postman](docs/api/postman/mortgage-platform-m5.postman_collection.json) |
| Events | [event-catalog.md](docs/architecture/event-catalog.md), JSON Schemas in [docs/architecture/events/](docs/architecture/events/) |
| Messaging operations | [messaging-runbook.md](docs/operations/messaging-runbook.md) |
| Demo & sign-off | [m5-demo-checklist.md](docs/operations/m5-demo-checklist.md), `bash scripts/m5-demo.sh` |

### Run the stack

```bash
cp .env.example .env            # optional; defaults work without it
docker compose up --build -d
docker compose ps               # postgres, localstack, mortgage-service, servicing-service, analytics-service -> healthy
curl localhost:8080/actuator/health; curl localhost:8081/actuator/health; curl localhost:8000/health
bash scripts/m5-demo.sh         # end-to-end demo incl. DLQ
```

Do **not** use `docker compose down -v` unless you intend to wipe the database volume (it re-seeds on next start).

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

# Repository contract checks (schemas <-> examples <-> catalog <-> Java producer records)
docker run --rm -v "$PWD":/w -w /w python:3.14.7-slim sh -c "pip install -q pytest jsonschema && python -m pytest -q tests/contract"
```

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

## 🛠️ Local Development & Reset Workflow
To reset and seed your local PostgreSQL environment:
```powershell
.\database\scripts\reset-dev-db.ps1