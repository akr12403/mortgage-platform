# AWS IAM Matrix (M8 Task 8.1)

Each workload gets one IAM role, and each role has one inline policy that grants only the actions that workload calls, on the exact resources it uses. Nothing else is allowed: anything not listed here is implicitly denied.

| Item | Where |
| --- | --- |
| Role manifest | [`infrastructure/aws/iam/roles.json`](../../infrastructure/aws/iam/roles.json) |
| Policy templates | [`infrastructure/aws/iam/policies/`](../../infrastructure/aws/iam/policies/) and [`trust/`](../../infrastructure/aws/iam/trust/). They use `${ACCOUNT_ID}`, `${REGION}` and resource-name placeholders, so no account id is committed. |
| Resource names | [`infrastructure/aws/resources.conf`](../../infrastructure/aws/resources.conf), following `guides/standards.md` naming |
| Apply / verify / remove | `scripts/aws/iam-apply.sh`, `scripts/aws/iam-verify.sh`, `scripts/aws/teardown.sh` |
| Static guard (CI) | `python3 tests/security/test_iam_policies.py`, run in the `sast` job |

**Account and Region:** the AWS sandbox project in `us-east-2`. The "new AWS experience" pins a project to one Region, so this differs from the `us-east-1` default in `guides/standards.md`. LocalStack keeps using `us-east-1`. Every resource is tagged `Project=mortgage-intelligence`, `Environment=dev`, `Team=capstone`.

## Matrix: role → services → actions → resources

| Role | Used by | Trusted principal | Service | Actions | Resources (exact ARNs) |
| --- | --- | --- | --- | --- | --- |
| `mortgage-api-role` | mortgage-service (Java, 8080) | developer session (local runs) | SNS | `sns:Publish` | topic `capstone-mortgage-lifecycle-dev` |
| `mortgage-servicing-role` | servicing-service (Java, 8081) | developer session | SQS | `sqs:ReceiveMessage`, `sqs:DeleteMessage` | queue `capstone-mortgage-servicing-dev` |
| `mortgage-analytics-role` | mortgage-analytics-service (Python, 8000) and the pipeline scripts | developer session | S3 (documents) | `s3:PutObject` | `capstone-mortgage-docs-dev/mortgages/*` |
| | | | S3 (data lake) | `s3:PutObject` | `capstone-mortgage-analytics-dev/raw/pg-export/*` |
| | | | | `s3:GetObject` | `…/raw/pg-export/*`, `…/curated/delinquency_report/*` |
| | | | | `s3:ListBucket` (only with `s3:prefix` = those two prefixes) | bucket `capstone-mortgage-analytics-dev` |
| | | | Glue | `glue:StartJobRun`, `glue:GetJobRun`, `glue:GetJobRuns` | job `capstone-mortgage-delinquency-etl-dev` |
| | | | DynamoDB | `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `BatchWriteItem` | table `CapstoneMortgageLookup-dev` |
| | | | SQS | `sqs:ReceiveMessage`, `sqs:DeleteMessage` | queue `capstone-mortgage-analytics-dev` |
| `lambda-doc-processor-role` | Lambda `capstone-mortgage-doc-processor-dev` (Task 8.3) | `lambda.amazonaws.com` | S3 | `s3:GetObject` | `capstone-mortgage-docs-dev/mortgages/*` |
| | | | DynamoDB | `dynamodb:PutItem` | table `CapstoneMortgageDocumentMetadata-dev` |
| | | | CloudWatch Logs | `logs:CreateLogStream`, `logs:PutLogEvents` | log group `/aws/lambda/capstone-mortgage-doc-processor-dev` (created by the deploy script with 7-day retention, so no `CreateLogGroup`) |
| `mortgage-glue-etl-role` | Glue job `capstone-mortgage-delinquency-etl-dev` (Task 8.5) | `glue.amazonaws.com` | S3 | `s3:GetObject` | `…analytics-dev/raw/pg-export/*`, `…/glue/*` (script and schema) |
| | | | | `s3:PutObject`, `s3:DeleteObject` | `…analytics-dev/curated/delinquency_report/*` (delete lets a re-run overwrite) |
| | | | | `s3:ListBucket` (prefix-restricted) | bucket `capstone-mortgage-analytics-dev` |
| | | | CloudWatch Logs | `logs:CreateLogGroup`, `CreateLogStream`, `PutLogEvents` | `/aws-glue/*` log groups |

The handbook asks for three roles. Two more are added for least privilege, rather than giving extra permissions to the required three:
- **`mortgage-servicing-role`:** servicing-service is a separate process with a separate job, so it doesn't share `mortgage-api-role`.
- **`mortgage-glue-etl-role`:** Glue needs a role it can assume, and the analytics service should not be able to write the curated zone.

### Why each boundary exists

| Boundary | What it prevents |
| --- | --- |
| The analytics role can **write** documents but not **read** or delete them | A compromised analytics container can't download borrower documents or destroy the upload history. Only the Lambda reads uploads. |
| Only the Glue role writes `curated/` | The curated report is only ever produced by the ETL job, so reconciliation (Task 8.6) compares PostgreSQL against Glue output, never against a hand-edited file. |
| Glue can't write `raw/`; nothing can delete `raw/` | The raw export is the audit trail for each pipeline run. |
| `ListBucket` is restricted by prefix | There's no bucket-wide listing, so other prefixes (for example `glue/` job assets) stay invisible to the analytics role. |
| DynamoDB access is item-level only (`GetItem`, `PutItem`, `UpdateItem`, `BatchWriteItem`), with no `Scan`, `Query`, `DeleteTable` or `UpdateTable` | Reads go by partition key only, which matches the Task 8.4 access pattern, and there's no table administration. |
| No role has `iam:*`, `sts:AssumeRole` or `iam:PassRole` | No role can escalate privileges or hand a role to a new resource. Passing roles to Lambda and Glue is done once, by the developer, in the deploy scripts. |
| Each SQS consumer gets only receive and delete on its own queue | No `SendMessage`, `PurgeQueue` or other queue's messages. Dead-letter redrive stays an operator action (`docs/operations/messaging-runbook.md`). |

## How workloads get credentials (no access keys)

- **Lambda and Glue:** the service assumes the role; AWS supplies rotating credentials.
- **Local containers (this project runs them with docker compose):**
  - The developer's `aws login` session (role `AccountFullAccessRole`) assumes the workload's role, which gives 1-hour credentials.
  - Those credentials go into the container only. No long-lived keys exist in `.env`, the repo or any image.
  - The trust policy names that exact role ARN, filled in by `iam-apply.sh`.
  - The wiring is added in Task 8.2.
- **M9 (ECS/Terraform):** the app roles' trust changes from the developer session to `ecs-tasks.amazonaws.com`, and the policies stay the same.

## Verification

Static check, with no AWS needed; it runs in CI:

```bash
python3 tests/security/test_iam_policies.py
```

It renders every template and fails on any of these:
- wildcard actions, `Resource "*"`, or Region/account/bucket wildcards;
- `NotAction` or `NotResource`, or `iam:PassRole`;
- a wildcard or unexpected trust principal;
- a role missing from this matrix;
- a hard-coded account id or access key.

It also checks that the over-permissioned exercise file **is** flagged.

In AWS:

```bash
aws login --profile capstone-dev --region us-east-2
bash scripts/aws/iam-apply.sh     # IAM Access Analyzer validation, then create or update the roles
bash scripts/aws/iam-verify.sh    # 39 policy-simulator cases (log permissions are checked against log-group ARNs, which is what CloudWatch Logs authorizes): needed actions allowed, the rest denied
```

Every simulation passes `aws:RequestedRegion=us-east-2`, as a real request would. The sandbox project has an AWS-managed guardrail policy (SCP `RegionFloor`) that explicitly denies any request outside the project Region. In the simulator, a request with no Region counts as outside, so without the context entry every allowed case shows `explicitDeny`. The two layers work together: these roles define what a workload may do, and the account guardrails cap what anyone can do (for example, nothing outside `us-east-2`, and no Glacier storage classes).

`iam-verify.sh` prints one line per case. Excerpt:

```text
  mortgage-analytics-role
    PASS allow s3:PutObject           capstone-mortgage-docs-dev/mortgages/MTG-1001/sample.pdf document upload endpoint
    PASS deny  s3:GetObject           capstone-mortgage-docs-dev/mortgages/MTG-1001/sample.pdf cannot read borrower documents back
    PASS deny  s3:PutObject           capstone-mortgage-analytics-dev/curated/delinquency_report/part-0000.csv only Glue writes curated
    PASS deny  dynamodb:Scan          table/CapstoneMortgageLookup-dev                 no full-table scans
```

## Mini exercise: fix an over-permissioned policy

The **before** file is [`infrastructure/aws/iam/exercise/lambda-doc-processor-overpermissioned.json`](../../infrastructure/aws/iam/exercise/lambda-doc-processor-overpermissioned.json). It's the usual "make it work" policy for the document Lambda and is never applied to AWS. The **after** file is the real [`policies/lambda-doc-processor-role.json`](../../infrastructure/aws/iam/policies/lambda-doc-processor-role.json).

```bash
diff -u infrastructure/aws/iam/exercise/lambda-doc-processor-overpermissioned.json \
        infrastructure/aws/iam/policies/lambda-doc-processor-role.json
```

```diff
     {
-      "Sid": "S3Access",
+      "Sid": "ReadUploadedDocumentForValidation",
       "Effect": "Allow",
-      "Action": "s3:*",
-      "Resource": "*"
+      "Action": "s3:GetObject",
+      "Resource": "arn:aws:s3:::${DOCS_BUCKET}/${DOCS_UPLOAD_PREFIX}*"
     },
     {
-      "Sid": "DynamoAccess",
+      "Sid": "WriteDocumentMetadataItem",
       "Effect": "Allow",
-      "Action": "dynamodb:*",
-      "Resource": "arn:aws:dynamodb:*:*:table/*"
+      "Action": "dynamodb:PutItem",
+      "Resource": "arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${DOC_METADATA_TABLE}"
     },
     {
-      "Sid": "Logs",
+      "Sid": "WriteOwnLogGroupOnly",
       "Effect": "Allow",
-      "Action": "logs:*",
-      "Resource": "*"
-    },
-    {
-      "Sid": "PassRoleForLater",
-      "Effect": "Allow",
-      "Action": "iam:PassRole",
-      "Resource": "*"
+      "Action": [
+        "logs:CreateLogStream",
+        "logs:PutLogEvents"
+      ],
+      "Resource": "arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/lambda/${LAMBDA_FUNCTION}:*"
     }
```

| Before | Risk | After |
| --- | --- | --- |
| `s3:*` on `*` | Read, overwrite or delete **every** bucket in the account, change bucket policies, or make a bucket public | `s3:GetObject` on `docs/mortgages/*` only: the one call the validator makes |
| `dynamodb:*` on every table in every Region | Scan or delete the lookup table, or drop tables | `dynamodb:PutItem` on the metadata table only |
| `logs:*` on `*` | Read or delete any log group (including audit evidence) and change retention | `CreateLogStream` and `PutLogEvents` on its own log group only (`…:log-group:/aws/lambda/<function>:*`, the form CloudWatch Logs authorizes against) |
| `iam:PassRole` on `*` | Hand any role, including admin, to a resource it creates: privilege escalation | Removed. The function never creates resources. |

How it was fixed:
1. List the API calls the code actually makes: `get_object` and `put_item`, plus the Lambda runtime's log writes.
2. Map each call to one action.
3. Scope each action to the exact ARN, using placeholders for the account and Region.
4. Run `test_iam_policies.py` and `iam-verify.sh`.

`test_iam_policies.py` reports 9 findings on the before file and none on the after file:

```text
S3Access: wildcard action s3:*
S3Access: Resource *
DynamoAccess: wildcard action dynamodb:*
DynamoAccess: Region/account wildcard in arn:aws:dynamodb:*:*:table/*
DynamoAccess: unscoped resource arn:aws:dynamodb:*:*:table/*
Logs: wildcard action logs:*
Logs: Resource *
PassRoleForLater: iam:PassRole is not needed by any service role
PassRoleForLater: Resource *
```

## Changing a policy

1. Edit the template in `infrastructure/aws/iam/policies/`. If a workload is new, add it to `roles.json` and to this matrix.
2. Run `python3 tests/security/test_iam_policies.py`.
3. Run `bash scripts/aws/iam-apply.sh`. It is idempotent, removes stale inline policies and warns about any manually attached managed policy.
4. Add a case to `iam-verify.sh` for the new permission and for the denial next to it, then run it.
5. Open a PR. The `sast` job reruns the guard.
