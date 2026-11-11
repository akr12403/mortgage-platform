# Service Level Objectives (M9 Task 9.3)

The SLIs are computed in Splunk (index `mortgage_dev`) from the `http_request` line that every service writes per request. The fields are defined in the [log contract](observability.md#log-contract). The SLIs and their alerts appear on the dashboard *Mortgage Platform: Service Health* ([`monitoring/splunk/`](../../monitoring/splunk/)).

## Payment API

The critical user journey is posting a borrower payment: `POST /api/v1/mortgages/{id}/payments` on `mortgage-service`. A payment that fails or hangs means a borrower may be marked late, and a delinquency event may be published wrongly.

| SLI | Definition | SLO | Error budget |
| --- | --- | --- | --- |
| **Payment success rate** | good requests / all requests. Good = status `< 500`; a `4xx` is the caller's error, not the service's | **99.5% over 30 days** (rolling) | 0.5% of requests, about 216 minutes of full outage a month at constant traffic |
| **Payment latency** | 95th percentile of `durationMs` (server time) | **p95 < 500 ms**, every 5-minute window | windows above 500 ms. Target: no more than 1% of the 5-minute windows in 30 days. |

### Queries

**Success rate (30 days):**
```text
index=mortgage_dev message=http_request service.name=mortgage-service http.method=POST http.route="/api/v1/mortgages/{id}/payments" earliest=-30d
| eval good=if('http.status'<500,1,0)
| stats count as total, sum(good) as good
| eval sli=round(good/total*100,3), budget_used_pct=round((total-good)/(total*0.005)*100,1)
```

**Latency (p95 per 5 minutes, and how many windows broke the SLO):**
```text
index=mortgage_dev message=http_request service.name=mortgage-service http.method=POST http.route="/api/v1/mortgages/{id}/payments" earliest=-30d
| bin _time span=5m
| stats perc95(durationMs) as p95 by _time
| eval breach=if(p95>500,1,0)
| stats count as windows, sum(breach) as breached, max(p95) as worst_p95
```

## Alerts

These are defined as code in [`monitoring/splunk/alerts.json`](../../monitoring/splunk/alerts.json). Each runs every minute over its window (the last 5 complete minutes, or 1 minute for the fast alerts), is tracked under *Activity → Triggered Alerts*, and is suppressed for 10 minutes after it fires. Payment searches leave out `429` (client throttling, not a service failure); throttled requests have their own dashboard panel.

| Alert | Fires when | Why this threshold | Runbook |
| --- | --- | --- | --- |
| Payment API failing now (fast burn) | in the last complete minute, ≥ 3 payment requests and ≥ 50% 5xx | a full outage pages within about 1–2 minutes. The 5-minute alerts are diluted by the healthy minutes before the failure, and took 3 min in the [2026-11-10 drill](rca-2026-11-10.md) (B-23). | [runbook](runbook.md#alert-payment-api-failing-now) |
| Payment API 5xx rate above 5% | more than 5% of at least 5 payment requests returned 5xx in 5 minutes | 10× the error rate the SLO allows. At that burn rate the month's budget lasts about 3 days, so it needs a person now. Slower burns show on the dashboard. | [runbook](runbook.md#alert-payment-api-5xx-rate) |
| Payment API p95 latency above 500 ms | p95 above 500 ms over at least 5 payment requests in 5 minutes | the latency SLO itself, measured per window | [runbook](runbook.md#alert-payment-api-latency) |
| Database unreachable | any service logged a database connection failure in the last complete minute | names the cause directly instead of the symptom (B-24) | [runbook](runbook.md#alert-database-unreachable) |
| Error spike in a service | a service logged 10 or more `ERROR` lines in 5 minutes | catches failures that aren't payment requests: the database, the broker, a consumer failing on poison messages | [runbook](runbook.md#alert-service-error-spike) |

The **minimum of 5 requests** keeps a single failed request on a quiet system from paging anyone.

## Scope and limits

- **The SLIs are measured at the service, not at the client.** Requests that never reach the service, such as network or DNS failures, don't count. With a load balancer (prod), its 5xx would be added.
- **Event processing** (servicing history and analytics updated after a payment) has no formal SLO yet. The dashboard shows consumer failures, and messages that fail 3 times go to the DLQs (see [messaging-runbook.md](messaging-runbook.md)). A candidate SLO: 99% of events processed within 60 s.
- **Locally the numbers come from test traffic.** The targets matter for a shared environment; locally they show that the measurement and the alerts work.
