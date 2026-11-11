# Resilience Patterns (M4 + M5)

M4 asks for "retry, timeout, circuit breaker, or a documented resilience pattern". This page records what each service does and why.

| Concern | Pattern | Where |
| --- | --- | --- |
| DB connection acquisition | **Timeout**: Hikari `connection-timeout` 30 s, `validation-timeout` 5 s, pool max 10, `max-lifetime` 30 min | `services/*/src/main/resources/application.yml` |
| DB outage during a request | **Fail fast + error envelope**: `DataAccessException` → 500 `INTERNAL_ERROR` with `correlationId` and no stack trace | `GlobalExceptionHandler` (covered by `DatabaseFailureIntegrationTest`) |
| Analytics DB connections | **Stale-connection check**: SQLAlchemy `pool_pre_ping=True` | `analytics/.../src/api/dependencies.py` |
| S3 upload (analytics) | **Retry + timeout**: botocore `max_attempts=3`, `connect_timeout=5`, `read_timeout=10`; failure → 502 `S3_UPLOAD_ERROR` | `analytics/.../src/services/s3_service.py` |
| AWS SDK (SNS/SQS, Java) | **Retry**: AWS SDK v2 standard retry policy (3 attempts, exponential backoff with jitter) | `AwsConfig`, `AwsSqsConfig` |
| Event consumption | **Retry → DLQ**: no ack on failure, redelivery after 30 s visibility timeout, DLQ after 3 receives | `EventConsumerService`, `localstack/init/...sh`, [messaging-runbook.md](../operations/messaging-runbook.md) |
| Duplicate delivery / client retries | **Idempotency**: `event_inbox` (consumer), payment `Idempotency-Key` (API) | `EventConsumerService`, `PaymentService` |
| Partial failure between services | **Async decoupling**: services never call each other synchronously; if servicing is down, events wait in SQS | ADR-002 |
| Poison messages | **Isolation**: DLQ plus ERROR log on the final attempt; unsupported `schemaVersion` is rejected | `EventConsumerService` |
| Liveness/readiness | **Health probes**: `/actuator/health` (liveness and readiness groups), `/health`; Docker `HEALTHCHECK`; compose starts services only after DB and messaging are ready | `docker/Dockerfile.*`, `docker-compose.yml` |

## Why no circuit breaker (yet)

A circuit breaker protects a caller from a failing **synchronous** dependency. In M5 no service calls another over HTTP. The only remote dependencies are PostgreSQL (bounded by pool timeouts) and AWS SNS/SQS/S3 (bounded by SDK retries). Async SQS delivery already gives the isolation a breaker would. If a synchronous call is added later (for example the M7 assistant calling mortgage-service), wrap it with Resilience4j `@CircuitBreaker` + `@TimeLimiter` and record that in an ADR.
