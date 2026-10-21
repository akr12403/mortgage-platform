# Project Scope & Requirements Definition

## Problem Statement
Traditional secondary mortgage servicing and portfolio management often suffer from fragmented data systems, delayed risk visibility, and labor-intensive document processing. Lenders and loan servicers frequently struggle to maintain real-time oversight of payment performance, delinquency escalations, and portfolio analytics across aging monolithic platforms. Establishing a modern, unified mortgage intelligence platform addresses these inefficiencies by streamlining loan origination data ingestion, simplifying payment processing tracking, automating document extraction, and surfacing predictive financial analytics for servicing operations.

## Objectives
- **Core API Delivery**: Expose baseline loan application and servicing history endpoints via REST APIs by Milestone 4.
- **Real-Time Analytics Pipeline**: Implement asynchronous event streaming to process loan status updates and calculate portfolio delinquency metrics within 2 seconds of event publication by Milestone 5.
- **AI-Powered Knowledge Assistant**: Deploy a Retrieval-Augmented Generation (RAG) assistant capable of executing Q&A over mortgage domain guidelines and borrower documents by Milestone 8.
- **Operational Auditability**: Enforce 100% auditable logging for all payment transactions, state transitions, and credential operations across containerized environments by Milestone 9.

## Milestone 5 Definition of Done
By the end of M5, the platform must meet the following production-grade objectives for a local, containerized environment:
- A documented microservice architecture with explicit ownership of database tables, API contracts, and events per service.
- Contract-first HTTP API definitions for mortgage lifecycle, servicing history, delinquency, and analytics endpoints.
- Lifecycle events routed over **SNS → SQS → consumer** with raw message delivery, redrive policy, deduplication, and DLQ visibility.
- Runnable local services via Docker Compose with health checks, explicit configuration, and reproducible startup.
- Live end-to-end demo scenario covering mortgage creation, approval, payment posting, delinquency triggering, and analytics aggregation.
- Runtime evidence for retry behavior, failed event processing, and consumer deduplication using the `event_inbox` store.
- Known implementation limits documented (shared database for reads, publish-after-commit instead of a transactional outbox, in-memory dedupe in the analytics consumer, no auth until M6) — see `docs/operations/m5-demo-checklist.md`.

## In-Scope Functionality
- **Borrower & Mortgage Onboarding**: Ingestion and management of borrower profiles, income verification data, and loan application lifecycles.
- **Underwriting Support**: Automated credit evaluation rules, debt-to-income (DTI) ratio calculations, and loan decisioning workflows.
- **Loan Servicing & Payments**: Real-time escrow management, payment schedule generation, principal/interest processing, and amortization tracking.
- **Delinquency Management**: Early warning indicators, delinquent loan categorization, and workout option workflows for defaulted accounts.
- **Portfolio Analytics**: Aggregated risk assessment dashboards, yield trends, performance projections, and event-driven metrics ingestion.
- **Document Management**: Secure document storage, metadata indexing, and automated text extraction.
- **AI Knowledge Assistant**: Intelligent conversational agent for domain policy queries and document retrieval.
- **Security & Operations**: Role-based access control (RBAC), containerized microservices orchestration, central logging, and secrets security.

## Out-of-Scope
- **Production Third-Party Integrations**: Direct live API integrations with Fannie Mae, Freddie Mac, or credit bureau production endpoints (e.g., Equifax, Experian).
- **Mobile Application Distribution**: Native iOS or Android mobile application releases targeting public app stores.
- **Live Financial Transactions**: Real-world automated clearing house (ACH) bank money movement or live securitization trading desk capabilities.

## Assumptions
- All testing and development activities will rely strictly on synthetic, non-PII borrower data.
- Local development will execute on macOS (ARM64) with runtime parity targeting Docker-based execution on a Windows VM baseline.
- Cloud deployment and infrastructure automation will utilize simulated sandbox environments and local container networking setups.

## Stakeholders
- **Product Owner Proxy**: Drives functional priorities, defines milestone acceptance criteria, and validates feature alignments against domain goals.
- **Servicing Operations Lead**: Oversees payment processing accuracy, delinquency management flows, and escrow tracking usability.
- **Compliance & Audit Officer**: Enforces regulatory compliance standards, zero-trust security controls, data privacy rules, and detailed audit trails.
- **DevOps & Platform Administrator**: Maintains repository health, container orchestration, cross-platform build parity, and automated testing infrastructure.

## Non-Functional Requirements (Initial)
- **Security**: All API traffic must enforce TLS encryption, JWT authentication, and strict separation of sensitive data stores.
- **Auditability**: Every loan state change, payment entry, and user permission change must generate an immutable, timestamped audit log.
- **Availability Targets**: Containerized services must support zero-downtime health probes with an initial service availability target of 99.5% in test environments.