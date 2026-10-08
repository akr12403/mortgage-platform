# Target User Personas

## 1. Underwriter
- **Role Summary**: Responsible for evaluating borrower creditworthiness, verifying financial documentation, assessing debt-to-income (DTI) metrics, and rendering loan approval or rejection decisions.
- **Goals**:
  - Evaluate loan risk rapidly and accurately using standardized rules.
  - Access underlying mortgage underwriting guidelines and policy documentation without leaving the decision interface.
  - Render verifiable loan decisioning logs for compliance reviews.
- **Pain Points**:
  - Fragmented borrower data across legacy origination systems.
  - Time-consuming manual calculations for complex debt and income scenarios.
- **Primary Capstone Features**:
  - **Automated Underwriting Engine**: DTI calculations, risk scoring, and rule-based approval workflows (Epic: *Underwriting*).
  - **Contextual Policy Assistant**: AI-driven Q&A over underwriting guideline documents (Epic: *AI Assistant*).

---

## 2. Servicing Agent
- **Role Summary**: Manages post-origination loan administration, processes borrower payment transactions, manages escrow adjustments, and responds to account inquiries.
- **Goals**:
  - Gain instant visibility into real-time loan statuses, current principal balances, and transaction histories.
  - Track scheduled payments, interest accruals, and escrow disbursements accurately.
- **Pain Points**:
  - Delays in payment ledger synchronization between transactional databases and agent portals.
  - Difficulty reconciling historical servicing events across legacy tabular logs.
- **Primary Capstone Features**:
  - **Servicing Dashboard & APIs**: Real-time access to loan servicing history, payment processing endpoints, and balance reconciliations (Epic: *Servicing*, Epic: *Payment*).

---

## 3. Risk Analyst
- **Role Summary**: Monitors secondary market portfolio health, analyzes delinquency trends, evaluates credit risk exposure, and generates executive risk summaries.
- **Goals**:
  - Track real-time portfolio delinquency metrics and default migration patterns.
  - Aggregate loan performance trends across geographic regions and borrower credit tiers.
- **Pain Points**:
  - Reliance on batch-processed end-of-month reporting rather than real-time data streaming.
  - Inability to perform dynamic filtering on large loan portfolio datasets without impacting transactional database performance.
- **Primary Capstone Features**:
  - **Real-Time Analytics Pipeline**: Event-driven performance metrics, portfolio yield tracking, and delinquency risk summaries (Epic: *Analytics*, Epic: *Delinquency*).

---

## 4. Administrator
- **Role Summary**: Manages system access controls, configures organizational roles, provisions internal user accounts, and configures global application settings.
- **Goals**:
  - Maintain centralized control over user provisioning and Role-Based Access Control (RBAC).
  - Enforce least-privilege security policies across all platform sub-services.
- **Pain Points**:
  - Manual user onboarding across multiple isolated microservice datastores.
  - Risk of unauthorized privilege escalation due to stale access permissions.
- **Primary Capstone Features**:
  - **Identity & Access Management (IAM)**: Centralized user/role provisioning endpoints and role-based route guardrails (Epic: *Security*, Epic: *Borrower Management*).

---

## 5. Security Analyst
- **Role Summary**: Enforces security posture, conducts routine access reviews, monitors platform audit logs, and supports incident response procedures.
- **Goals**:
  - Gain complete visibility into security events, authentication attempts, and authorization failures.
  - Verify that sensitive borrower PII and credentials remain fully encrypted and uncompromised.
- **Pain Points**:
  - Disjointed audit trails scattered across individual container logs.
  - Lack of immutable audit records for regulatory compliance reviews.
- **Primary Capstone Features**:
  - **Audit Logging & Security Controls**: Immutable audit event stream, secret management integration, and centralized vulnerability monitoring (Epic: *Security*, Epic: *Operations*).

---

## 6. Support Engineer
- **Role Summary**: Responsible for maintaining system availability, troubleshooting service failures, correlating application logs, and executing operational runbooks.
- **Goals**:
  - Rapidly trace error cascades and transaction failures across microservice boundaries.
  - Execute automated runbooks for service recovery, database health checks, and container redeployments.
- **Pain Points**:
  - High mean time to resolution (MTTR) when debugging distributed microservice interactions.
  - Unclear error context between API gateway routes and downstream backend services.
- **Primary Capstone Features**:
  - **Centralized Telemetry & Operations**: Distributed log correlation, health probe endpoints, and automated recovery runbooks (Epic: *Operations*).

---

## 7. Borrower (Optional / End User)
- **Role Summary**: The individual applying for a mortgage or managing an active mortgage loan through the platform's self-service interface.
- **Goals**:
  - Submit loan applications easily and upload required financial verification documents.
  - View current loan status, make online payments, and review upcoming payment schedules.
- **Pain Points**:
  - Lack of transparency during the loan decisioning and underwriting pipeline.
  - Difficulty getting immediate answers to policy or payment questions.
- **Primary Capstone Features**:
  - **Self-Service Borrower Portal**: Document upload workflows, application status tracking, and AI-powered help guidance (Epic: *Borrower Management*, Epic: *Document Management*, Epic: *AI Assistant*).