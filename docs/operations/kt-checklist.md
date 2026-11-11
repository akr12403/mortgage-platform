# Knowledge Transfer and Handover Checklist (M10 Task 10.6)

What an L1 or L2 engineer needs to support the platform, and a checklist to confirm the handover happened. Escalation levels and the go-live conditions are in the [readiness review](production-readiness.md#support-and-escalation).

## 1. Access

| What | Where | L1 | L2 | How to get it |
| --- | --- | --- | --- | --- |
| Source, pipeline, issues | GitHub `akr12403/mortgage-platform` | read | write | Repository invitation from the owner |
| Handbook (requirements, milestones) | GitHub `capstone-secondary-mortgage-intelligence-platform` | read | read | Same |
| Container images | GHCR `ghcr.io/akr12403/mortgage-platform/<service>` | read | read | Comes with repository access |
| Logs, dashboard, alerts | Splunk, index `mortgage_dev` (local: http://localhost:8002) | read | admin | Local: `bash scripts/splunk/local-up.sh` creates the admin login in `.env.splunk-local` |
| AWS dev (us-east-2) | AWS CLI profile `capstone-dev` (browser sign-in) | none | developer session | `aws login --profile capstone-dev --region us-east-2` |
| Secrets (`.env`: JWT secret, DB and seed passwords, LLM key) | Never in Git; one `.env` per machine from `.env.example` | none | per machine | Generated locally ([runbook: secrets](runbook.md#secrets-rotation)); the LLM key from the AI lead |
| Application users | 5 seed users, one per role: `admin@`, `underwriter@`, `servicing@`, `risk@`, `support@capstone.local` | `support@` | all | Password = `AUTH_SEED_PASSWORD` in that machine's `.env`; never share it in chat or tickets |

## 2. Systems and URLs

| Component | Local URL | Health | Code |
| --- | --- | --- | --- |
| mortgage-service (Java): borrowers, mortgages, payments, login | http://localhost:8080 | `/actuator/health` | `services/mortgage-service` |
| servicing-service (Java): servicing history, delinquency | http://localhost:8081 | `/actuator/health` | `services/servicing-service` |
| analytics-service (Python): portfolio and risk analytics | http://localhost:8000 | `/health` | `analytics/mortgage-analytics-service` |
| knowledge-assistant (Python): grounded policy Q&A | http://localhost:8001 | `/health`, `/health/ready` | `ai/mortgage-knowledge-assistant` |
| PostgreSQL 17 + pgvector | localhost:5432 | `pg_isready` | `database/` |
| LocalStack (SNS, SQS, S3) | http://localhost:4566 | | `localstack/` |
| Splunk (local) | http://localhost:8002 | | `monitoring/splunk/` |

AWS dev: ECS cluster `capstone-mortgage-dev` (services at 0 tasks), ECR `capstone-mortgage-dev/<service>`, SQS queues and DLQs `capstone-mortgage-*-dev`, Terraform state `capstone-mortgage-tfstate-<account>`. API contracts: [docs/api](../api/). Architecture: [docs/architecture](../architecture/).

## 3. Daily operations

| Task | How |
| --- | --- |
| Start / stop the local stack | `docker compose up -d` / `docker compose down` (README, *Local Development & Reset Workflow*) |
| Start log shipping and Splunk | `bash scripts/splunk/local-up.sh` (`--down` to stop) |
| Check every service | `curl` the health URLs above, or `docker compose ps` |
| Run the E2E journeys | `cd tests/e2e && npm ci && npm test` ([README](../../tests/e2e/README.md)) |
| Deploy to dev | `bash scripts/deploy/deploy-dev.sh sha-<commit>` ([runbook](runbook.md#how-a-change-reaches-dev)) |
| Roll back | `bash scripts/deploy/deploy-dev.sh <last good tag>` ([runbook](runbook.md#rollback)) |
| Check for drift | `bash scripts/terraform/tf.sh dev plan -detailed-exitcode` (exit 0 = none) |
| Redrive a DLQ | [messaging-runbook.md](messaging-runbook.md) |
| Rotate a secret | [runbook.md](runbook.md#secrets-rotation) |
| Verify backups (local) | `bash scripts/ops/backup-restore-check.sh` |
| Measure baseline performance | `python3 scripts/perf/smoke.py` |
| Security scan | `sh scripts/security-gates.sh all` |

## 4. Splunk queries L1 needs

```text
# Everything about one request or user action (the ID is in the X-Correlation-Id response header and every error body)
index=mortgage_dev correlationId="<id>" | sort _time | table _time service.name log.level message http.status durationMs

# Errors in the last 15 minutes, by service and type
index=mortgage_dev log.level=ERROR earliest=-15m | stats count by service.name, error.type

# Payment success rate and p95 (the SLO)
index=mortgage_dev message=http_request service.name=mortgage-service http.method=POST http.route="/api/v1/mortgages/{id}/payments" http.status!=429
| stats count as total, count(eval('http.status'>=500)) as failed, perc95(durationMs) as p95

# Database unreachable
index=mortgage_dev log.level=ERROR ("Database unavailable" OR "Connection is not available")

# Throttled requests (429) by route
index=mortgage_dev message=http_request http.status=429 | stats count by service.name, http.route
```

More in [observability.md](observability.md). Dashboard: *Mortgage Platform: Service Health* (`mortgage_platform_overview`).

## 5. Alerts and what to do

| Alert | First step | Runbook |
| --- | --- | --- |
| Database unreachable | Check the database container or instance; restart it | [section](runbook.md#alert-database-unreachable) |
| Payment API failing now (fast burn) | Follow one failed payment by `correlationId` | [section](runbook.md#alert-payment-api-failing-now) |
| Payment API 5xx rate above 5% | Same; check recent deploys | [section](runbook.md#alert-payment-api-5xx-rate) |
| Payment API p95 latency above 500 ms | Check the database and the latency panel by route | [section](runbook.md#alert-payment-api-latency) |
| Error spike in a service | *Latest errors* panel, then the trace | [section](runbook.md#alert-service-error-spike) |

Severity, roles and the incident record: [incident-response.md](incident-response.md). A worked example: the [RCA of the 2026-11-10 database outage](rca-2026-11-10.md).

## 6. Escalation

| Level | When | To |
| --- | --- | --- |
| L1 → L2 | The runbook step didn't fix it in 15 minutes; any SEV-1; any data correction; any deploy or rollback | Platform/backend lead (`@akr12403`) |
| L2 → SME | Suspected security incident or leaked secret; wrong or unsafe assistant answer; infrastructure change needed | Security lead or AI lead (`@akr12403`); review: Sumanth Donur |

Record every incident as a GitHub issue labelled `incident`, with the correlation IDs and times (UTC).

## 7. Known issues

Read [known-issues.md](known-issues.md) before the first on-call shift, especially K-1 (500 at the moment of a database failure), K-7 (no MFA, no token revocation), K-11 (manual deploys) and K-12 (no database in AWS).

## Handover session checklist

Tick each item during the session with the person taking over.

- [ ] Access granted and tested: GitHub, Splunk, AWS (L2), `.env` created on their machine (secrets never sent in chat)
- [ ] Walked through the architecture: 4 services, events through SNS/SQS, PostgreSQL, the assistant ([docs/architecture](../architecture/))
- [ ] Started the local stack and Splunk; all health checks green
- [ ] Ran the E2E journeys: 16/16 passed
- [ ] Found one request in Splunk by its correlation ID
- [ ] Read the dashboard and the 5 alerts; opened each runbook section
- [ ] Walked through the RCA of 2026-11-10 and the incident-response roles
- [ ] Did a dev deploy and a rollback with `deploy-dev.sh` (L2), or watched one
- [ ] Ran the backup/restore check
- [ ] Read the known issues and the go-live conditions
- [ ] Agreed escalation contacts and where incidents are recorded

Handover done by: ______  Taken over by: ______  Date: ______
