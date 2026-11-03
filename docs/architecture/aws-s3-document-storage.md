# S3 Document Storage (M8 Task 8.2)

Two buckets in the AWS sandbox (project Region `us-east-2`). Both follow the `guides/standards.md` naming, and both reuse the names from M3/M5 rather than adding new ones.

| Bucket | Purpose | Written by | Read by | Layout |
| --- | --- | --- | --- | --- |
| `capstone-mortgage-docs-dev` | Mortgage documents uploaded through `POST /api/v1/documents/upload` | `mortgage-analytics-role` (analytics-service) | `lambda-doc-processor-role` only (Task 8.3) | `mortgages/<mortgageExternalId>/<uuid>-<safe file name>` |
| `capstone-mortgage-analytics-dev` | Data lake for the Task 8.5 pipeline | `mortgage-analytics-role` → `raw/pg-export/`; `mortgage-glue-etl-role` → `curated/delinquency_report/` | analytics role (raw and curated), Glue role (raw and `glue/` assets) | `raw/pg-export/date=YYYY-MM-DD/…`, `curated/delinquency_report/…`, `glue/scripts/`, `glue/schemas/` |

The names live in `infrastructure/aws/resources.conf`. S3 names are global across all AWS accounts. If a name is taken, change it there and re-run `iam-apply.sh` (the policies reference it), then `s3-apply.sh`.

## Controls on every bucket

| Control | Setting | Why |
| --- | --- | --- |
| Block Public Access | All four settings on | No ACL or bucket policy can make an object public, even by mistake |
| Object Ownership | `BucketOwnerEnforced` (ACLs disabled) | Access is decided by IAM and the bucket policy only, never by per-object ACLs |
| Default encryption | SSE-S3 (`AES256`); the upload code also sends `ServerSideEncryption=AES256` | Every object is encrypted at rest. SSE-S3 is used instead of KMS because it has no key cost and there's no cross-account sharing to control; production would use a customer-managed KMS key (see `docs/operations/runbook.md`, key rotation). |
| Bucket policy [`s3/bucket-policy.json`](../../infrastructure/aws/s3/bucket-policy.json) | Deny `s3:*` when `aws:SecureTransport` is false, or when `s3:TlsVersion` < 1.2 | Data in transit is always TLS 1.2+, for every caller, the developer included |
| Lifecycle (optional in the handbook; done) | `mortgages/`, `raw/pg-export/` and `curated/delinquency_report/` expire after 30 days; incomplete multipart uploads are aborted after 1 day | Non-production data doesn't pile up. Production would replace expiry with a records-retention schedule. |
| Tags | `Project=mortgage-intelligence`, `Environment=dev`, `Team=capstone` | Cost and ownership tracking |
| Account guardrails (AWS-managed, project level) | Only `us-east-2`; no Glacier storage classes; no access from outside the account's organization | Hard limits that apply even if a bucket policy is wrong |

Versioning is off. In this dev sandbox the 30-day expiry and teardown are simpler without it. Production would turn versioning on for the documents bucket, with noncurrent-version expiry, so an overwrite or delete can be undone.

## Upload path: no long-lived keys

```text
client --JWT--> analytics-service (container) --HTTPS, SigV4 with STS session credentials--> S3 capstone-mortgage-docs-dev
                       ^
                       | 1-hour credentials for mortgage-analytics-role
developer `aws login` session --sts:AssumeRole--> mortgage-analytics-role     (scripts/aws/compose-aws-up.sh)
```

- **Service code:** `src/services/s3_service.py` uses the default credential chain only. It has no key parameters.
  - `S3_ENDPOINT_URL=""` sends S3 calls to real AWS while SQS stays on LocalStack through `AWS_ENDPOINT_URL`.
  - `S3_REGION` sets the bucket Region.
  - When `S3_ENDPOINT_URL` isn't set, the client behaves as before: LocalStack, or Moto in tests.
- **Local run:** [`docker-compose.aws.yml`](../../docker-compose.aws.yml) overrides only `analytics-service`.
  - The credentials reach it through the environment of `compose-aws-up.sh` and are never written to a file.
  - They are temporary STS credentials, so an access-key-ID check sees `ASIA…`, never `AKIA…`.
  - They stop working after 1 hour (the AWS limit when one role session assumes another). After that, uploads return `502 S3_UPLOAD_ERROR` and you run the script again.
- **What the role allows:** `s3:PutObject` on `mortgages/*` and nothing else in this bucket. A compromised analytics container can't list, read, overwrite outside its prefix, or delete documents.
- **Java services:** they have no S3 path. mortgage-service only publishes to SNS, and servicing-service only consumes SQS. Their roles have no S3 permissions at all (`aws-iam-matrix.md`).
- **On ECS (M9):** the same code gets credentials from the task role through the container credentials endpoint, with no script. Only the trust policy changes.

## Commands

```bash
aws login --profile capstone-dev --region us-east-2
bash scripts/aws/s3-apply.sh        # create/harden both buckets (idempotent)
bash scripts/aws/s3-verify.sh       # 14 config checks + 8 live allow/deny tests as mortgage-analytics-role

docker compose up --build -d        # local stack (if not running)
bash scripts/aws/compose-aws-up.sh  # analytics-service -> real S3 with role credentials
docker compose up -d analytics-service   # back to LocalStack-only
```

What `s3-verify.sh` proves, live and as the analytics role:

| Request | Expected |
| --- | --- |
| Upload to `mortgages/MTG-0000/…` over HTTPS | Allowed, stored with `AES256` |
| Read that document back / delete it | `AccessDenied` (only the Lambda reads uploads) |
| Upload outside `mortgages/` | `AccessDenied` |
| Upload over plain HTTP | `AccessDenied` (bucket policy `DenyInsecureTransport`) |
| Write `raw/pg-export/` / write `curated/` | Allowed / `AccessDenied` (only Glue writes curated) |
| Anonymous `GET` of the object from the internet | HTTP 403 |

The test objects are synthetic and are deleted at the end of the run.
