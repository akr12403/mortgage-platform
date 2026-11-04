# M8 Demo & Sign-off Checklist

Automated demo: `bash scripts/m8-demo.sh` (about 12 minutes; `PAUSE=1` waits for Enter before each step, for rehearsal).
- It follows the milestone's 5-step demo scenario.
- It finishes with analytics-service back on LocalStack-only.
- One run costs one Lambda invocation, one Glue run (about $0.0005) and a few S3/DynamoDB requests. The sandbox is on the AWS Free plan.

## Before the demo

```bash
cd ~/projects/mortgage-platform
docker compose up --build -d && docker compose ps
aws login --profile capstone-dev --region us-east-2
aws sts get-caller-identity --profile capstone-dev          # AccountFullAccessRole in the sandbox project
bash scripts/aws/iam-verify.sh                              # 39/39: roles still match the repo
PAUSE=1 bash scripts/m8-demo.sh
```

If the sandbox was torn down, re-create it in this order. Each script is idempotent, and together they take about 5 minutes:

```bash
bash scripts/aws/iam-apply.sh
bash scripts/aws/s3-apply.sh
bash scripts/aws/lambda-deploy.sh
bash scripts/aws/lookup-deploy.sh
bash scripts/aws/lookup-load.sh
bash scripts/aws/pipeline-deploy.sh
```

Have these open: [aws-iam-matrix.md](../architecture/aws-iam-matrix.md) (step 1), [aws-dynamodb-mortgage-lookup.md](../architecture/aws-dynamodb-mortgage-lookup.md#partition-key-exercise-session-29) (step 5), and [data-pipeline-runbook.md](data-pipeline-runbook.md#schema-drift-session-30-exercise) (questions on drift).

## Demo scenario (the milestone's demo script)

| # | Show (time) | What to say | Pass criteria |
| --- | --- | --- | --- |
| 1 | **IAM matrix for one service role** (2 min) | One role per workload, one inline policy, exact ARNs, no `*` actions, no access keys. The analytics role can **write** documents but not read them back, and can read curated data but not write it. CI runs a policy guard, and the IAM simulator proves both sides of each rule. | `mortgage-analytics-role` rows shown; its 15 simulator cases PASS |
| 2 | **Upload a document → Lambda log line** (3 min) | The upload uses 1-hour role credentials. S3 `ObjectCreated` triggers the Lambda, which reads the first 1 KB, validates the type and writes one DynamoDB metadata item. Its JSON log line carries the **upload's correlation ID**. | `200 UPLOADED`; a log line with the same `correlationId`, `"status":"VALIDATED"`, `"documentType":"DEED"` |
| 3 | **Run the pipeline; show the curated file** (3 min) | PostgreSQL export → raw → Glue, which checks the input and every output row against the committed schema → curated plus a manifest. Only the Glue role can write curated. The analytics API reads the curated report. | `SUCCEEDED`; `curated rows 18 (PostgreSQL mortgages 18)`, balances equal; the report API answers |
| 4 | **Reconciliation output** (2 min) | 8 checks. Row count must match exactly and the balance sum must be within ±0.01; the per-row, export-control and manifest checks catch what totals hide. The severity-band data-quality check is a WARN, not a FAIL. | `RESULT: PASS`; WARN `DQ_SEVERITY_BAND` (MTG-1005) |
| 5 | **Partition key choice** (2 min) | `mortgageExternalId`: high cardinality, every access is by one mortgage, and DynamoDB hashes keys so sequential IDs still spread. `borrowerExternalId` alone, `status` and dates are rejected. Bulk loads are shuffled with backoff. | Table shown; live GetItem for MTG-1002 |

## Validation (from the milestone)

- [x] **Upload document → Lambda runs → metadata visible.**
  - `lambda-verify.sh` (2026-11-03): the real PDF came back `VALIDATED`, the text file posing as a PDF came back `REJECTED [MAGIC_BYTES_MISMATCH]`, and both DynamoDB items and both JSON log lines were found by correlation ID.
  - Through the API: correlation ID `13d0a1fc-…` produced a Lambda line for MTG-1002, `DEED`, `VALIDATED`.
- [x] **DynamoDB lookup returns a mortgage by key.**
  - `GET /api/v1/lookup/mortgages/MTG-1002` → 279,000.00 (`pg-bulk-load`).
  - After a 1,850.00 payment it returned **277,150.00**, `source: event`, `lastEventType: PaymentReceived` (2026-11-03).
- [x] **Raw and curated prefixes populated after a pipeline run.** `raw/pg-export/date=2026-11-04/`: 4 CSVs + `_export_manifest.json`. `curated/delinquency_report/date=2026-11-04/`: `part-0000.csv` + `_manifest.json` (18 rows, 5,169,399.96).
- [x] **Reconciliation report PASS on the seed export.** `reconcile.sh`: 8/8 checks PASS (WARN `DQ_SEVERITY_BAND` for MTG-1005), recorded for 4 consecutive runs.
- [x] **Schema drift scenario documented with before/after.** In the [runbook](data-pipeline-runbook.md#schema-drift-session-30-exercise):
  - **`fail` mode:** FAILED with `SchemaDriftError`, and an EventBridge alert arrived about 70 s later. The curated output was untouched and reconciliation still PASSed.
  - **`evolve` mode:** SUCCEEDED, with the drift recorded in the manifest.
  - **Permanent-fix procedure** documented.

## Definition of Done → evidence

| DoD item | Evidence |
| --- | --- |
| IAM configured with least privilege and documented | 5 roles, each with one inline policy and exact ARNs ([matrix](../architecture/aws-iam-matrix.md)). IAM Access Analyzer validation on every apply. **39/39** simulator cases. `test_iam_policies.py` in CI fails on wildcards, `PassRole`, `NotAction`, public principals and committed account IDs. Over-permission mini exercise: before/after diff plus the 9 findings the guard reports. |
| S3 integrated with encryption and no public access | Both buckets: Block Public Access 4/4, ACLs disabled, SSE-S3 default (+ explicit on upload), deny non-TLS and TLS < 1.2, 30-day dev lifecycle, tags. `s3-verify.sh` **14 config + 8 live checks** PASS, including an anonymous GET → 403 and plain HTTP → AccessDenied ([doc](../architecture/aws-s3-document-storage.md)). |
| Lambda workflow demonstrated | `capstone-mortgage-doc-processor-dev` (python3.14, arm64): S3 trigger, type validation, DynamoDB metadata, JSON logs, error alarm stub, zip deploy command documented ([doc](../architecture/aws-document-lambda.md)). 9 unit tests in CI. Live runs above. |
| Messaging enhanced (Kinesis or documented SQS pattern) | [ADR-003](../adr/ADR-003-sqs-only-messaging-no-kinesis.md): SNS → SQS only. Kinesis needs the Paid plan, the volume is under 1 msg/s, and consumers need per-message retry and a DLQ. **Enhancement:** the analytics consumer updates the DynamoDB lookup with conditional writes (stale and duplicate safe; failures go to the DLQ). |
| DynamoDB lookup use case demonstrated | `CapstoneMortgageLookup-dev` (PK `mortgageExternalId`), bulk load 18/18, read API, live event update ([doc](../architecture/aws-dynamodb-mortgage-lookup.md)) |
| Data pipeline PostgreSQL → S3 → Glue → Curated implemented | `pipeline-run.sh` → Glue Python shell job (12 s, about $0.0005), committed [schema file](../../infrastructure/glue/schemas/delinquency_report.schema.json), curated report API, [runbook](data-pipeline-runbook.md) with schedule, owners and failure steps. 13 ETL unit tests in CI. |
| Reconciliation implemented | `reconcile.sh` / `src/services/reconcile.py`: 8 checks, documented tolerances, JSON report, exit code. 7 unit tests. |
| Schema drift scenario tested and documented | Strict `fail` mode by default, plus an EventBridge alert rule; opt-in `evolve` mode; live before/after recorded in the runbook. 5 drift unit tests. |
| Merged to develop via reviewed PR(s) | PRs **#101–#106** (Tasks 8.1–8.6). Every PR had the three security checks green (secrets, SAST including the IAM guard and Lambda/Glue tests, dependencies). Solo project, so review is by the author plus the gates (see the M6 limits). Peer review is below. |

## Implementation requirements (from the milestone)

| Requirement | How it is met |
| --- | --- |
| Tag resources `Project=mortgage-intelligence`, `Environment=dev` | Every role, bucket, table, function, log group, alarm, Glue job and rule is tagged, plus `Team=capstone` (`resources.conf`) |
| No access keys in Git; use IAM roles for Lambda/ECS tasks | Developer access is `aws login` (browser sign-in, up to 12 h). Workloads use role credentials: Lambda and Glue get service-issued ones, local containers get 1-hour STS credentials passed through the environment only. The CI guard blocks committed key IDs and account IDs. ECS task roles: [compute awareness](../architecture/aws-compute-awareness.md). |
| Cost awareness: tear down or use sandbox quotas | Free plan (no charges possible), on-demand tables, a 0.0625-DPU job, 7–30-day log retention, 30-day object expiry. `scripts/aws/teardown.sh` removes all 18 M8 resources plus the bucket trigger, in a safe order (dry run verified). |

## Security review of M8

The threat model has **T-33 to T-40**:
- IAM role misuse;
- developer session compromise;
- S3 exposure;
- malicious uploads;
- data-lake tampering or unreconciled data;
- schema drift;
- a stale lookup cache;
- cost or orphaned resources.

The risk register adds **R-21 to R-24**, and **R-08** drops from 10 Medium to 5 Low because the M8 bucket controls are now in place. Two commitments carried over from M7 haven't happened, and both are recorded rather than hidden:
- The AI key's move to Secrets Manager is moved to M9 (R-20).
- Malware scanning (B-13) is moved to M9.

## Deviations from the handbook (recorded)

| Handbook | Implemented | Why |
| --- | --- | --- |
| `AWS_REGION=us-east-1` (standards) | `us-east-2` for the AWS sandbox; LocalStack stays `us-east-1` | The "new AWS experience" project is pinned to one Region (assigned by country) |
| Kinesis stream | SNS → SQS only ([ADR-003](../adr/ADR-003-sqs-only-messaging-no-kinesis.md)) | The handbook allows this: Kinesis isn't on the Free plan, and volume and semantics favour SQS |
| 3 roles | 5 roles (+ `mortgage-servicing-role`, `mortgage-glue-etl-role`) | Least privilege: separate processes don't share permissions, and Glue needs its own assumable role |
| DynamoDB `MortgageLookup` | `CapstoneMortgageLookup-dev` (+ `CapstoneMortgageDocumentMetadata-dev` for Lambda metadata) | The `guides/standards.md` name; a separate table for a separate access pattern |
| SSE-S3 or KMS | SSE-S3 | No key cost and no cross-account sharing; SSE-KMS with a customer-managed key comes with the M9 Terraform (B-12) |
| Glue (Spark implied) | Glue **Python shell** | Kilobytes of data; about 1/32 of a Spark run's minimum capacity (0.0625 vs 2 DPU); same contract and checks ([compute awareness](../architecture/aws-compute-awareness.md#etl-sizing-glue-python-shell-vs-glue-spark-vs-emr)) |
| Java/Python upload paths on IAM roles | Python only | Only analytics-service uploads; the Java services have no S3 path and their roles have no S3 permissions |

## After sign-off

`bash scripts/aws/teardown.sh` removes everything M8 created. Re-create any time with the commands above. The sandbox's Free plan ends automatically; nothing runs or bills while it's idle.

## Sign-off

- [ ] **Reviewed by a peer or the instructor** at the M8 review session: demo run, IAM matrix, ADR-003 and pipeline runbook read, T-33 to T-40 and R-21 to R-24 agreed. Reviewer and date: ____________________
