# M5 Demo & Sign-off Checklist

Automated run: `bash scripts/m5-demo.sh` (about 3 minutes). Each step below says what to show and what "pass" looks like.

## Before the demo

```bash
cd ~/projects/mortgage-platform
cp -n .env.example .env   # since M6: set JWT_SECRET and AUTH_SEED_PASSWORD in .env (the demo script logs in with it)
docker compose up --build -d
docker compose ps        # postgres, localstack, 3 services "healthy"; db-migrate & messaging-init "Exited (0)"
```

Run the tests (commands are in the root `README.md` under **Testing**). All three suites must be green.

## Demo scenario (maps to the milestone's demo script)

| # | Show | Pass criteria |
| --- | --- | --- |
| 1 | **Create mortgage → `MortgageCreated`** (script step 1). Optional decoupling proof: `docker compose stop servicing-service`, create a mortgage, show `ApproximateNumberOfMessages=1` on `capstone-mortgage-servicing-dev`, then `docker compose start servicing-service` and watch it drain | 201, `status: PENDING`; mortgage-service log `Published MortgageCreated eventId=…`; history shows `MORTGAGE_CREATED` |
| 1b | **Approval workflow stub → `LoanApproved`** (step 2) | 200, `status: ACTIVE`; history `LOAN_APPROVED` |
| 2 | **Post payment → `PaymentReceived` consumed; history updated** (steps 3–4) | balance reduced; history `PAYMENT_POSTED`; replay with the same `Idempotency-Key` returns `Idempotent-Replayed: true` and adds **no** second history row |
| 2b | **Delinquency transition → `PaymentMissed` + `LoanDelinquent`** (step 5) | mortgage `DELINQUENT`; `GET :8081/…/delinquency` shows `daysPastDue ≥ 30`, `severity`; analytics delinquency rate increases |
| 2c | **Correlation ID** (step 6) | the same UUID appears in the HTTP response header, mortgage-service log, event envelope, and servicing consumer log |
| 3 | **Break consumer → DLQ** (step 7) | servicing log: `ERROR … attempt 1/3`, `2/3`, `final attempt 3/3; SQS will move … to the DLQ`; DLQ depth +1 after about 90–120 s; no history row for `MTG-0000` |
| 4 | **`docker compose ps` all healthy** (step 8) | health status comes from the Dockerfile `HEALTHCHECK` (`/actuator/health`, `/health`) |

Useful manual commands:

```bash
Q=http://localhost:4566/000000000000
docker compose exec -T localstack awslocal sqs get-queue-attributes --queue-url $Q/capstone-mortgage-servicing-dev --attribute-names All
docker compose exec -T localstack awslocal sqs receive-message --queue-url $Q/capstone-mortgage-servicing-dlq-dev --attribute-names All --visibility-timeout 5
docker inspect --format '{{json .State.Health}}' mortgage-service | python3 -m json.tool
# since M6 the APIs need a token; e.g. TOKEN=<accessToken from POST localhost:8080/api/v1/auth/login>
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/analytics/event-stats | python3 -m json.tool
```

## Validation (from the milestone)

- [ ] Publish test event; consumer processes within expected time (servicing history updated within ~5 s)
- [ ] Force consumer failure → message lands in the DLQ (demo step 7)
- [ ] All three services start in containers and pass the health check
- [ ] Event catalog matches implemented types (`EventSchemaContractTest` + `tests/contract/test_event_contracts.py` green)

## Definition of Done → evidence

| DoD item | Evidence in repo |
| --- | --- |
| Service boundaries and ownership documented | `docs/architecture/application-architecture.md`, `service-ownership-matrix.md`, `docs/adr/ADR-002-microservices-decomposition.md` |
| API contracts published for each service | `docs/api/{mortgage-service,servicing-service,mortgage-analytics-service}-openapi.yaml`, Postman collection in `docs/api/postman/` |
| Event schemas created and cataloged | `docs/architecture/events/*.schema.json`, `docs/architecture/event-catalog.md` |
| SNS/SQS integration working with retries | `EventPublisherService`, `EventConsumerService`, analytics `event_consumer.py`; demo steps 1–5 |
| DLQ configured and demonstrated | `localstack/init/ready.d/01-create-mortgage-messaging.sh`; demo step 7 |
| Dockerfiles for three services | `docker/Dockerfile.*` (multi-stage, non-root, `HEALTHCHECK`) |
| Containers run with health checks validated | `docker compose ps` healthy |
| Messaging runbook | `docs/operations/messaging-runbook.md` |
| Merged to develop via reviewed PR(s) | PR from `feature/M5-task5-fix` → `develop` with a reviewer approval |

## Known limits (stated, not hidden)

- One shared PostgreSQL instance with single-writer-per-table ownership. Separate schemas or databases are future work (ADR-002).
- Publish-after-commit, not a transactional outbox. An SNS outage right after commit loses that event, and the loss is logged at ERROR.
- The analytics consumer dedupes in memory, so a restart forgets seen IDs. That's acceptable because its only side effect is an idempotent snapshot refresh.
- (Resolved in M6) Authentication and RBAC now protect all APIs; the approval stub records the approver role from the JWT.
- LocalStack has no persistence; restarting it recreates empty queues.
