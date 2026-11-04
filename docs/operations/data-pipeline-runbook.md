# Data Pipeline Runbook: PostgreSQL → S3 Raw → Glue → S3 Curated → Analytics (M8 Task 8.5)

```text
PostgreSQL (mortgage_intel)
  │ 1. export: 4 tables, report columns only (no borrower PII) + control totals     scripts/aws/pipeline-run.sh
  ▼
s3://capstone-mortgage-analytics-dev/raw/pg-export/date=YYYY-MM-DD/
      mortgage.csv  borrower.csv  delinquency.csv  payment.csv  _export_manifest.json
  │ 2. Glue Python shell job capstone-mortgage-delinquency-etl-dev (role mortgage-glue-etl-role)
  │    input columns checked against the schema → join → derive → output rows checked → write
  ▼
s3://capstone-mortgage-analytics-dev/curated/delinquency_report/date=YYYY-MM-DD/
      part-0000.csv  _manifest.json      (one row per mortgage; columns = schema file)
  │ 3. read by analytics-service (mortgage-analytics-role: read-only on curated/)
  ▼
GET :8000/api/v1/analytics/curated/delinquency-report[?date=]     (ADMIN, UNDERWRITER, RISK_ANALYST)
```

| Item | Value |
| --- | --- |
| ETL code | [`infrastructure/glue/delinquency_report_etl.py`](../../infrastructure/glue/delinquency_report_etl.py): standard library plus boto3, Python 3.9 |
| Column schema (contract) | [`infrastructure/glue/schemas/delinquency_report.schema.json`](../../infrastructure/glue/schemas/delinquency_report.schema.json): input columns per raw table, output columns with types, enums, patterns and primary key. The job reads the deployed copy at `s3://…/glue/schemas/`. |
| Job | Python shell 3.9, 0.0625 DPU, timeout 10 min, `MaxRetries 0`, `MaxConcurrentRuns 1`, library set `analytics` |
| Cost | About $0.44/DPU-hour × 0.0625 DPU, with a 1-minute minimum: **about $0.0005 per run**. Covered by the Free plan credits. |
| Tests | `python3 -m unittest discover -s infrastructure/glue/tests -v` (8 tests, S3 faked, run in CI); analytics `tests/test_curated_report.py` (Moto) |

## Schedule and owners

| | |
| --- | --- |
| **Schedule** | **Manual, on demand** (`pipeline-run.sh`), once per business day before the morning risk review. The source PostgreSQL runs in docker compose on a developer machine, so AWS can't reach it and an AWS-side schedule (Glue trigger or EventBridge) can't run the export. **In M9**, with PostgreSQL in AWS (RDS), the plan is an EventBridge Scheduler rule at 06:00 UTC that starts a small export task and then the Glue job (`StartJobRun --arguments --RUN_DATE=<yesterday>`). |
| **Partition** | `date=YYYY-MM-DD`, the export day in UTC. One run per day. Re-running a day **replaces** that day's curated output (idempotent); raw files for the day are overwritten by the new export. |
| **Pipeline owner** | Data engineering (capstone: the developer on duty) owns the export, the Glue job and the schema file |
| **Consumer owner** | Risk analytics owns the report API and the morning review. They are notified when a run fails or a reconciliation doesn't PASS (Task 8.6). |
| **Change control** | The schema file, the ETL and the export SQL change in the **same PR**. A column change bumps `version` in the schema file. |
| **Retention** | Raw and curated objects expire after 30 days (dev lifecycle rule, Task 8.2). Glue logs are kept 7 days. |

## Run it

```bash
docker compose up --build -d                       # PostgreSQL with data
aws login --profile capstone-dev --region us-east-2
bash scripts/aws/pipeline-deploy.sh                # once, and after any change to the ETL or schema
bash scripts/aws/pipeline-run.sh                   # export -> raw -> Glue -> curated, prints the manifest
RUN_DATE=2026-11-04 bash scripts/aws/pipeline-run.sh     # a specific partition
bash scripts/aws/compose-aws-up.sh                 # analytics-service on AWS S3, then:
curl -s localhost:8000/api/v1/analytics/curated/delinquency-report -H "Authorization: Bearer $ADMIN_TOKEN"
```

A successful run ends like this (first run, 2026-11-04 partition):

```text
  OK   SUCCEEDED in 12s of execution
  {"timestamp": "2026-11-04T00:52:07.486+00:00", "level": "INFO", "service": "glue-delinquency-etl", "message": "ETL finished", "rowCount": 18, "outstandingBalanceTotal": "5169399.96", "delinquentCount": 8, …}
  curated rows 18 (PostgreSQL mortgages 18), balance 5169399.96 (PostgreSQL 5169399.96), delinquent 8, schema v1, pipeline run pr-…
```

**Tracing one run:** `pipeline-run.sh` creates a pipeline run ID (`pr-<UTC timestamp>-<8 hex>`) and passes it to the job as `--PIPELINE_RUN_ID`, because Glue doesn't give a Python shell job its own run ID. The same ID appears in:
- `raw/…/_export_manifest.json`;
- every job log line;
- `curated/…/_manifest.json`;
- the report API's `source.pipelineRunId`.

The script prints the Glue `JobRunId` next to it, and the job's log streams are named after the Glue run ID.

## Who can do what

| Identity | Raw `raw/pg-export/` | Curated `curated/delinquency_report/` | Glue job |
| --- | --- | --- | --- |
| `mortgage-analytics-role` (export upload, report API) | write, read | **read only** | start + watch this one job |
| `mortgage-glue-etl-role` (the job) | read | write + delete (re-run) | n/a |
| Developer session | (admin) | (admin) | deploy (`create-job`/`update-job`, `iam:PassRole`) |

Nobody but the Glue job writes the curated zone, so the report and the Task 8.6 reconciliation always compare PostgreSQL with Glue's output.

## Failure handling

The run script prints the job's JSON log lines from `/aws-glue/python-jobs/output` and `/error`, stream = job run ID. For an older run:

```bash
aws glue get-job-runs --job-name capstone-mortgage-delinquency-etl-dev --max-items 5 --profile capstone-dev \
  --query 'JobRuns[].[Id,JobRunState,StartedOn,ExecutionTime,ErrorMessage]' --output table
aws logs filter-log-events --log-group-name /aws-glue/python-jobs/error --log-stream-names <JobRunId> --profile capstone-dev
```

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Step 1 fails: `start the local stack first` or a psql error | PostgreSQL not running, or credentials in `.env` changed | `docker compose up -d postgres`; check `POSTGRES_USER`/`POSTGRES_DB` in `.env`; re-run |
| Step 2 `AccessDenied` on `put-object` | The key isn't under `raw/pg-export/`, or `iam-apply.sh` hasn't been run since a policy change | `bash scripts/aws/iam-verify.sh`; fix, re-run |
| Job `FAILED`: `SchemaContractError: mortgage.csv is missing required column(s) …` | **Schema drift**: the export no longer has a column the contract needs (renamed or dropped in PostgreSQL) | Don't edit the curated data. Fix the export SQL, or change the schema and ETL in one PR, bump `version`, run `pipeline-deploy.sh`, re-run the day. Task 8.6 covers the drift scenario and the added-column case. |
| Job `FAILED`: `SchemaContractError: row N: <column>=… violates …` | Bad source data, such as a new status value or a malformed ID | Check the row in PostgreSQL. If the value is legitimate, extend the enum in the schema (version bump) and redeploy. If not, fix the data at the source. |
| Job `FAILED`: `NoSuchKey raw/pg-export/date=…/payment.csv` | Partial export or upload | Re-run `pipeline-run.sh` for the same `RUN_DATE`; it re-exports everything |
| Job `FAILED`: `AccessDenied` writing curated | Glue role policy changed or the bucket was renamed | `iam-verify.sh` (`mortgage-glue-etl-role` cases); `pipeline-deploy.sh` |
| Job `TIMEOUT` (10 min) | Data far larger than expected (today it takes seconds) | Check the source row counts in `_export_manifest.json`. A Python shell job is single-node: above about 1 GB, move to a Glue Spark job (M10). |
| `ConcurrentRunsExceededException` | A run is already going (max 1) | Wait for it, or `aws glue batch-stop-job-run` if it's stuck |
| API `404 NOT_FOUND` | No curated partition for that date | Run the pipeline for that date; `GET …/delinquency-report/dates` lists what exists |
| API `502 CURATED_SCHEMA_MISMATCH` | A curated file was written by another schema version | Re-run that date with the current job |
| API `503 CURATED_UNAVAILABLE` | analytics-service is in LocalStack-only mode, or the role credentials expired (1 h) | `bash scripts/aws/compose-aws-up.sh` |

**A failed run never leaves partial curated output.** Every check runs **before** the job deletes or writes anything for the date. The previous good output for that date stays in place until a run succeeds.

## Verification

Task 8.6 (`scripts/aws/reconcile.sh`) reconciles PostgreSQL against curated output:
- row count, with 0 difference allowed;
- outstanding balance sum, within ± 0.01.

It also documents the schema drift scenario.
