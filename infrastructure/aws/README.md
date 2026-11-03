# infrastructure/aws (M8)

AWS sandbox definitions for Milestone 8. Resources are created by the scripts in `scripts/aws/`, which are idempotent and run from the repo root. Terraform replaces these scripts in M9.

| Path | What it holds |
| --- | --- |
| `resources.conf` | Resource names, Region, profile and tags. There are no secrets and no account id. |
| `iam/roles.json` | One entry per workload role: its trust policy and its permission policy |
| `iam/policies/*.json` | Least-privilege permission policies (templates using `${ACCOUNT_ID}`, `${REGION}` and resource names) |
| `iam/trust/*.json` | Who may assume each role |
| `iam/exercise/` | The over-permissioned "before" policy for the Task 8.1 mini exercise. It is never applied. |
| `s3/bucket-policy.json` | TLS-only bucket policy, applied to both buckets (Task 8.2) |
| `s3/lifecycle-*.json` | Dev cleanup rules per bucket (30-day expiry by prefix; abort stale multipart uploads) |
| `lambda/doc_processor/` | Document processor Lambda: `handler.py` and its unit tests (Task 8.3) |
| `dynamodb/document-metadata-table.json` | Metadata table written by the Lambda (PK `mortgageExternalId`, SK `s3Key`, TTL) |

Role-by-role detail: [docs/architecture/aws-iam-matrix.md](../../docs/architecture/aws-iam-matrix.md). Buckets and the upload path: [docs/architecture/aws-s3-document-storage.md](../../docs/architecture/aws-s3-document-storage.md). Document Lambda: [docs/architecture/aws-document-lambda.md](../../docs/architecture/aws-document-lambda.md).

## Prerequisites (once)

- AWS CLI v2, version 2.32.0 or later (`brew install awscli`), and `python3`.
- The sandbox project's Region is `us-east-2`:

  ```bash
  aws configure set region us-east-2 --profile capstone-dev
  ```

There are no access keys. Each session starts with:

```bash
aws login --profile capstone-dev --region us-east-2      # browser sign-in; credentials last up to 12 h
aws sts get-caller-identity --profile capstone-dev
```

The scripts always use profile `capstone-dev` in `us-east-2`. They ignore `AWS_ENDPOINT_URL` (LocalStack) and any key variables in your shell. `.env` and docker compose keep pointing at LocalStack in `us-east-1`, so the local stack is unaffected.

## Commands

```bash
python3 tests/security/test_iam_policies.py   # static least-privilege guard (no AWS needed, also runs in CI)
python3 -m unittest discover -s infrastructure/aws/lambda/doc_processor/tests   # Lambda unit tests (CI too)
bash scripts/aws/iam-apply.sh                 # validate (IAM Access Analyzer) + create/update the roles
bash scripts/aws/iam-verify.sh                # policy simulator: 39 allow/deny cases must match
bash scripts/aws/s3-apply.sh                  # create/harden both buckets (Task 8.2)
bash scripts/aws/s3-verify.sh                 # bucket config + live allow/deny tests as mortgage-analytics-role
bash scripts/aws/compose-aws-up.sh            # analytics-service uploads to real S3 with 1-hour role credentials
bash scripts/aws/lambda-deploy.sh             # document Lambda + metadata table + S3 trigger + error alarm (Task 8.3)
bash scripts/aws/lambda-verify.sh             # live: valid PDF -> VALIDATED, fake PDF -> REJECTED, JSON log lines
bash scripts/aws/teardown.sh                  # remove the Lambda pieces, empty + delete the buckets, delete the roles (asks first; --yes to skip)
```

Rendered policies, which contain the account id, are written to `reports/aws/`. That folder is git-ignored.

## Cost

The sandbox is on the AWS Free plan, so it cannot be charged. Credits and the plan end date are shown in the console account menu. Still, run `teardown.sh` when M8 is signed off.
