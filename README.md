# Mortgage Intelligence & Servicing Platform

The Enterprise Mortgage Platform is an event-driven, microservices-based system designed to streamline the entire mortgage loan lifecycle—from initial borrower application and automated underwriting to servicing, payment processing, delinquency workflows, portfolio risk analytics, and AI-assisted document intelligence. Engineered with security, auditability, and scalability at its core, the platform integrates Java/Spring microservices, Python data analytics, event streaming, and cloud-native infrastructure.

---

## Master Progress Tracker

| ID | Milestone | Week | Doc | Status |
| --- | --- | --- | --- | --- |
| **M1** | Foundation & Architecture | 1 | [docs/requirements/project-scope.md](docs/requirements/project-scope.md) | **Completed** |
| **M2** | Agile & Data Foundation | 2 | `docs/milestones/m02.md` | Planned |
| **M3** | Python Analytics | 3 | `docs/milestones/m03.md` | Planned |
| **M4** | Java / Spring Backend | 4–5 | `docs/milestones/m04.md` | Planned |
| **M5** | Microservices & Events | 6 | `docs/milestones/m05.md` | Planned |
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

## Getting Started & Engineering Standards

Before contributing to this repository, review our core engineering practices and setup guidelines:

1. Read the **[Engineering Standards](docs/requirements/engineering-standards.md)** to understand code review rules, testing benchmarks, and zero-secrets policies.
2. Follow our **Git Workflow**:
   - Primary integration branch: `develop`
   - Production branch: `main`
   - Feature branches: `feature/<milestone>-<short-description>` (e.g., `feature/M1-root-readme`)
   - Commit convention: `type(scope): summary` (e.g., `docs(requirements): update README with milestone traceability`)

---

## Project Repository Information

- **Repository Remote URL**: [https://github.com/akr12403/mortgage-platform](https://github.com/akr12403/mortgage-platform)
- **Team Members**:
  - Akshay Kasthurirangan