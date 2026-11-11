# Mortgage Analytics Service

Python (FastAPI) service providing portfolio analytics, data normalization, S3 document storage, and — from M5 — an optional SQS consumer that refreshes a portfolio snapshot when lifecycle events arrive. Port `8000`, health at `GET /health`. Contract: [`docs/api/mortgage-analytics-service-openapi.yaml`](../../docs/api/mortgage-analytics-service-openapi.yaml).

## Portfolio analytics & formulas

`src/repositories/mortgage_repository.py` (SQL, used by the API) and `src/analytics/portfolio.py` (pandas) compute:

* **Total mortgages**: count of all mortgage rows.
* **Active / delinquent**: counts by `status` (`ACTIVE`, `DELINQUENT`).
* **Outstanding balance total**: sum of `outstanding_balance`.
* **Delinquency rate** (canonical, `guides/standards.md`): `DELINQUENT / (ACTIVE + DELINQUENT)` — `PENDING` and `CLOSED` mortgages are excluded from the denominator.
* **Borrower risk summary**: per `borrower_external_id`, active+delinquent mortgage count, outstanding balance, delinquent count.
* **Payment trends**: monthly `POSTED` amount and on-time ratio (`paid_date <= due_date`).

## Event consumer (M5, optional queue)

When `SQS_QUEUE_ANALYTICS_EVENTS` is set, a background thread long-polls `capstone-mortgage-analytics-dev` (subscribed to the `capstone-mortgage-lifecycle-dev` SNS topic). Each lifecycle event refreshes the portfolio snapshot. It dedupes on `eventId` (bounded in-memory cache — the snapshot refresh is naturally idempotent), acknowledges only after success, and logs failures at ERROR; after 3 receives SQS moves the message to `capstone-mortgage-analytics-dlq-dev`. Inspect with `GET /api/v1/analytics/event-stats`.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt  # runtime deps + pytest/moto/httpx
uvicorn src.api.main:app --reload --port 8000
```

`requirements.txt` holds runtime dependencies only (what the Docker image installs); test tooling lives in `requirements-dev.txt`.

## Tests

S3 calls are mocked with **moto**; the event consumer is tested without AWS.

```bash
python -m pytest -q tests
```
