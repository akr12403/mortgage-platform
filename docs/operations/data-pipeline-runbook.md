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
| Tests | `python3 -m unittest discover -s infrastructure/glue/tests -v` (13 tests including the schema drift cases, S3 faked, run in CI); analytics `tests/test_curated_report.py` (Moto) and `tests/test_reconcile.py` |

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

## Reconciliation

Run `bash scripts/aws/reconcile.sh`, optionally with `RUN_DATE=…`, **right after** `pipeline-run.sh`. It runs `src/services/reconcile.py` in a one-off analytics-service container, as `mortgage-analytics-role`, which can read curated and raw. It compares **PostgreSQL now** with the **curated partition**, and also with the **control totals the export wrote** (`_export_manifest.json`). It prints a table and saves the JSON report to `reports/aws/reconciliation/date=YYYY-MM-DD.json` (git-ignored).

| Check | Compares | Tolerance | On breach |
| --- | --- | --- | --- |
| `ROW_COUNT` | PostgreSQL `mortgage` rows vs curated rows | **0 difference** | FAIL |
| `BALANCE_SUM` | `sum(outstanding_balance)` PostgreSQL vs curated | **± 0.01** currency unit | FAIL |
| `KEY_SET` | Mortgage IDs missing from or extra in curated | none | FAIL (lists up to 10) |
| `ROW_BALANCE` | Per-mortgage balance | ± 0.01 each | FAIL. Catches offsetting errors that leave the total unchanged. |
| `DELINQUENT_COUNT` | `delinquency` rows vs `is_delinquent=true` | 0 | FAIL |
| `MANIFEST` | Curated `_manifest.json` `rowCount` vs data file rows | equal | FAIL |
| `EXPORT_CONTROL` | Curated vs the export's own counts and balance | rows 0, balance ± 0.01 | FAIL: the pipeline lost or changed data between export and curated |
| `DQ_SEVERITY_BAND` | Severity vs days past due: 30–59 `MODERATE`, 60–89 `SEVERE`, 90+ `CRITICAL` (delinquency playbook) | n/a | **WARN only**: a source-data quality issue, reported but not "fixed" by the pipeline |

**Result:** `PASS` when no check fails. WARNs are listed but don't fail the run. The exit code is `0` for PASS, `1` for FAIL, and `2` when the reconciliation couldn't run, for example because the curated zone isn't readable.

**If it FAILs:**
1. **Only the live checks fail and `EXPORT_CONTROL` passes.** PostgreSQL changed after the export (a payment was posted, for example). Re-run `pipeline-run.sh` then `reconcile.sh` for the same date, with no writes in between.
2. **`EXPORT_CONTROL` fails.** Raw and curated disagree, which means a pipeline defect. Don't publish the report. Compare `raw/…/mortgage.csv` with `curated/…/part-0000.csv` for the IDs in `KEY_SET`/`ROW_BALANCE`, fix the ETL, add a unit test, redeploy and re-run.
3. **`MANIFEST` fails.** The curated file was replaced outside the job. Re-run the pipeline for the date. Only the Glue role can write curated, so check CloudTrail for who did it.

**If it WARNs on `DQ_SEVERITY_BAND`:** tell the servicing owner. The delinquency playbook says severity is assigned once and doesn't escalate automatically (a known backlog item), so mislabelled loans need a manual review. The first run found **MTG-1005**: 88 days past due, labelled `CRITICAL`, band says `SEVERE`.

## Schema drift (Session 30 exercise)

**Policy:** `SCHEMA_DRIFT_MODE`, a job argument, defaults to `fail`.

| Change in the raw export | `fail` (default) | `evolve` (opt-in, one run) |
| --- | --- | --- |
| A required column is **missing** or renamed | Run FAILS (`SchemaContractError`) | Run FAILS. Never tolerated. |
| An **unexpected column is added** | Run FAILS (`SchemaDriftError`) → **alert** | Run succeeds. The column is ignored for the output (the curated contract is unchanged), logged at WARN, and recorded in `_manifest.json` `schemaDrift`. |
| A value outside the output contract (new status, bad ID) | Run FAILS (output validation) | Run FAILS |

**Alert (fail-with-alert):**
- An EventBridge rule, `capstone-mortgage-delinquency-etl-dev-failed`, matches `Glue Job State Change` for this job when the state is `FAILED`, `TIMEOUT`, `ERROR` or `STOPPED`.
- It delivers the event to the log group `/aws/events/capstone-mortgage-pipeline-alerts-dev` (30 days). `pipeline-run.sh` prints the alert event after a failed run.
- **M9:** add an SNS topic with an e-mail or Slack subscription as a second target of the same rule.

**Every check runs before anything is deleted or written,** so a drift failure leaves the previous curated output for that date in place, and `reconcile.sh` still PASSes against it.

**Scenario: someone adds `property_state` to the mortgage export.** `DRIFT_COLUMN` adds `'CA' AS property_state` to the export SQL.

```bash
# Before: strict contract, the run fails and an alert is raised; curated output unchanged
DRIFT_COLUMN=property_state bash scripts/aws/pipeline-run.sh
bash scripts/aws/reconcile.sh                     # still PASS against the previous good output
# Short-term remedy (one run): tolerate the additive column, recorded in the manifest
DRIFT_COLUMN=property_state SCHEMA_DRIFT_MODE=evolve bash scripts/aws/pipeline-run.sh
bash scripts/aws/reconcile.sh                     # PASS; manifest schemaDrift = {"mortgage": ["property_state"]}
```

Before and after, as recorded on 2026-11-04 (partition `date=2026-11-04`, 18 mortgages, balance 5,169,399.96):

| Run | Pipeline run | Glue state | Alert | Curated partition | Reconciliation |
| --- | --- | --- | --- | --- | --- |
| Baseline (no drift) | `pr-20261104T012512Z-4503ab13` | SUCCEEDED (12 s) | none | written, schema v1, 13 columns | **PASS** (8 checks; WARN `DQ_SEVERITY_BAND`: MTG-1005) |
| Drift `property_state`, `fail` | `pr-20261104T013612Z-d43915e8` | **FAILED**: `SchemaDriftError: unexpected column(s) in the raw export {'mortgage': ['property_state']} (schema v1)` | **`ALERT 2026-11-04T01:37:39Z Glue Job State Change … -> FAILED`** in the alert log group, about 70 s after the failure | **unchanged**: reconcile still reads the baseline's run `pr-…012512Z` | **PASS** against the kept output |
| Drift `property_state`, `evolve` | `pr-20261104T013910Z-b78845e7` | SUCCEEDED (12 s) + WARN `Schema drift tolerated` | none | rewritten. The manifest records `schemaDrift: {"mortgage": ["property_state"]}`. The data file is unchanged: same 13 columns, 1988 bytes. | **PASS** |
| Clean re-run | `pr-20261104T014221Z-d5e5ef9b` | SUCCEEDED (15 s) | none | rewritten, no drift recorded | **PASS** |

**The permanent fix** is a PR, not a mode switch:
1. Decide whether the new column belongs in the report.
2. If yes:
   - add it to `sources.mortgage` and to `columns` in `delinquency_report.schema.json`;
   - bump `version` to 2;
   - write it in `transform()`;
   - add a unit test;
   - update the report reader if it uses the column.
3. If no, add it to `sources.mortgage` only, so it's known and not drift. Bump the version.
4. Merge, run `pipeline-deploy.sh`, re-run the day, and run `reconcile.sh`. The curated manifest shows the new `schemaVersion`.
