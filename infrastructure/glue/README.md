# infrastructure/glue (M8 Task 8.5)

| File | Purpose |
| --- | --- |
| `delinquency_report_etl.py` | Glue Python shell job: raw PostgreSQL export → curated `delinquency_report` (Python 3.9, stdlib + boto3) |
| `schemas/delinquency_report.schema.json` | Column contract: required input columns per raw table, output columns with types, enums, patterns and primary key. The job loads the deployed copy from `s3://capstone-mortgage-analytics-dev/glue/schemas/`. |
| `tests/` | `python3 -m unittest discover -s infrastructure/glue/tests -v` (runs in CI) |

Deploy with `bash scripts/aws/pipeline-deploy.sh` and run with `bash scripts/aws/pipeline-run.sh`. Operations, schedule, owners and failure steps: [docs/operations/data-pipeline-runbook.md](../../docs/operations/data-pipeline-runbook.md).
