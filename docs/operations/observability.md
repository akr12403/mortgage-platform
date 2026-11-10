# Observability (M9 Task 9.3)

All four services write **one JSON object per line to stdout**, with the same field names. Docker (locally) or the ECS log driver (AWS) collects the lines, and Splunk HTTP Event Collector receives them into index `mortgage_dev`. A single search therefore works across Java and Python services, and one correlation ID follows a request through every service it touches.

This page is the **log contract**. Splunk setup, the dashboard, the alerts and the SLOs build on it.

## Log contract

| Field | On | Example | Notes |
| --- | --- | --- | --- |
| `@timestamp` | every line | `2026-11-10T03:16:36.150Z` | UTC, milliseconds |
| `log.level` | every line | `INFO`, `WARN`, `ERROR` | Logback level names in all services; Python's `WARNING` is written as `WARN` |
| `service.name` | every line | `mortgage-service`, `servicing-service`, `mortgage-analytics-service`, `mortgage-knowledge-assistant` | |
| `log.logger` | every line | `com.capstone.mortgage.service.PaymentService`, `http.access` | |
| `message` | every line | `http_request`, `Processed PaymentReceived for MTG-1001 …` | |
| `correlationId` | every line written while handling a request or an event | `7c9e6679-7425-40de-944b-e07fc1f90ae7` | The caller's `X-Correlation-ID`, or a new UUID. It's returned in the response header and in every error body. Events carry it in their envelope, and both consumers restore it. |
| `http.method` | `http_request` lines | `POST` | |
| `http.route` | `http_request` lines | `/api/v1/mortgages/{id}/payments` | The route **template**, never the raw path. That keeps mortgage numbers out of the field and the number of routes small. `unmatched` means the request was rejected before routing (unknown path, or 401/403 from the security filter in the Java services). |
| `http.status` | `http_request` lines | `201` | a number |
| `durationMs` | `http_request` lines | `12.3` | a number: server time from the first filter to the response |
| `user` | Java lines after authentication | `servicing@capstone.local` | from the JWT subject (MDC) |
| `eventId`, `eventType` | consumer lines | | servicing-service (MDC) and analytics-service |
| `error.type`, `error.message`, `error.stack_trace` | lines logged with an exception | | ECS error fields |

Notes on the format:
- **Java** uses Spring Boot's built-in structured logging in ECS format: `StructuredLogEncoder` in `logback-spring.xml`, with no extra library. Spring may nest objects (`{"log":{"level":"INFO"}}`) where Python writes dotted keys (`"log.level"`). Splunk's JSON extraction flattens both to the same field name, `log.level`.
- **Python** uses `src/observability.py`. It is the same file in both services, and a contract test checks they stay identical.

**Never logged:** request or response bodies, query strings, headers (`Authorization` included), tokens or secrets. Tests in every service check that a bearer token sent with a request doesn't appear in any log line.

**Not request traffic:** container health checks (`/actuator/health`, `/health`, every 15 s) produce no `http_request` line.

## Examples

A payment, then the same correlation ID in the event consumer of another service:

```json
{"@timestamp":"2026-11-10T03:16:36.150Z","log":{"level":"INFO","logger":"http.access"},"service":{"name":"mortgage-service"},"message":"http_request","correlationId":"7c9e6679-7425-40de-944b-e07fc1f90ae7","user":"servicing@capstone.local","http.method":"POST","http.route":"/api/v1/mortgages/{id}/payments","http.status":201,"durationMs":48.2}
{"@timestamp":"2026-11-10T03:16:36.402Z","log.level":"INFO","service.name":"mortgage-analytics-service","log.logger":"src.messaging.event_consumer","message":"Processed PaymentReceived for MTG-1001 (eventId=…, correlationId=7c9e6679-…)","correlationId":"7c9e6679-7425-40de-944b-e07fc1f90ae7","eventId":"…","eventType":"PaymentReceived"}
```

## Reading the logs locally

```bash
docker compose logs --no-log-prefix mortgage-service | grep '^{' | jq -c '{t:."@timestamp", lvl:(.log.level // ."log.level"), msg:.message, cid:.correlationId}'
docker compose logs --no-log-prefix | grep '^{' | jq -c 'select(.correlationId=="<id>")'     # one request, all services
```

## Splunk searches (index `mortgage_dev`)

| Question | Search |
| --- | --- |
| Everything for one request | `index=mortgage_dev correlationId="7c9e6679-7425-40de-944b-e07fc1f90ae7" \| sort _time` |
| Errors of one service, last hour | `index=mortgage_dev service.name=mortgage-service log.level=ERROR earliest=-1h` |
| Request rate by service | `index=mortgage_dev message=http_request \| timechart span=1m count by service.name` |
| 5xx rate | `index=mortgage_dev message=http_request \| eval err=if('http.status'>=500,1,0) \| timechart span=5m avg(err) by service.name` |
| Payment latency p95 | `index=mortgage_dev message=http_request http.route="/api/v1/mortgages/{id}/payments" http.method=POST \| timechart span=5m p95(durationMs)` |

The handbook's example `service=mortgage-service level=ERROR` maps to `service.name=… log.level=…`.

## Splunk

```text
service stdout (JSON) -> Docker fluentd log driver -> log-shipper (Fluent Bit) -> Splunk HEC (TLS) -> index mortgage_dev
```

- **Shipping is an overlay:** [`docker-compose.splunk.yml`](../../docker-compose.splunk.yml).
  - **Host, port, token and index come from the environment**, never from a file in Git.
  - **Fluent Bit** parses each line into fields and adds the container name, sending them with sourcetype `mortgage:app:json`.
  - **`docker compose logs` still works:** Docker keeps a local copy (dual logging). Services never wait for the shipper (`fluentd-async`).
- **Local Splunk** for building and testing: `bash scripts/splunk/local-up.sh`. In one command it:
  - generates its own credentials;
  - creates the index, the HEC token, the dashboard and the alerts;
  - starts the stack;
  - proves a request is searchable by its correlation ID.
- **Splunk objects as code:** [`monitoring/splunk/`](../../monitoring/splunk/) holds the dashboard and alerts, with instructions for importing them into another Splunk.
- **SLIs, SLOs and the alert thresholds:** [slo.md](slo.md). **What to do when an alert fires:** [runbook.md#alerts](runbook.md#alerts).

### Troubleshooting

| Symptom | Check |
| --- | --- |
| Nothing arrives in `mortgage_dev` | `docker compose logs log-shipper`. A `401`/`403` is a wrong token, or a token not allowed to write to `mortgage_dev`. `connection refused` is the wrong host or port, or Splunk isn't up yet. |
| Events arrive but have no fields | The sourcetype must be `mortgage:app:json`, not `_json`. Search-time JSON extraction applies to the custom sourcetype. |
| A service's lines are missing | It was started without the overlay. Run `docker compose -f docker-compose.yml -f docker-compose.splunk.yml up -d <service>` again. |
| Local Splunk is slow or doesn't start | It's amd64-only. On Apple silicon, enable Rosetta in Docker Desktop and give Docker at least 6 GB of memory. The first start takes several minutes. |
