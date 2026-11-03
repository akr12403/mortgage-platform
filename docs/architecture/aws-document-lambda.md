# Document Processing Lambda (M8 Task 8.3)

When a document lands in `s3://capstone-mortgage-docs-dev/mortgages/`, the function `capstone-mortgage-doc-processor-dev` does three things:
- validates the file;
- records one metadata item in DynamoDB;
- writes one structured JSON log line.

```text
POST /api/v1/documents/upload (analytics-service, correlationId C)
  └─ s3:PutObject mortgages/MTG-1002/<uuid>-deed.pdf   (SSE-S3; metadata correlation-id=C, document-type=DEED)
       └─ S3 event s3:ObjectCreated:* (prefix mortgages/)  ──async invoke──▶  Lambda doc-processor
              1. ranged GET (first 1 KB only)  →  validate type / magic bytes / size
              2. dynamodb:PutItem  CapstoneMortgageDocumentMetadata-dev  {PK MTG-1002, SK s3Key, status, …}
              3. one JSON log line  {timestamp, level, service, correlationId C, message, mortgageId, …}
                 └─ CloudWatch Logs /aws/lambda/capstone-mortgage-doc-processor-dev (7 days)
                       └─ metric AWS/Lambda Errors ──▶ alarm capstone-mortgage-doc-processor-dev-errors (stub)
```

| Item | Value |
| --- | --- |
| Code | [`infrastructure/aws/lambda/doc_processor/handler.py`](../../infrastructure/aws/lambda/doc_processor/handler.py): standard library plus the boto3 that comes with the runtime, so there are no packaged dependencies |
| Runtime | `python3.14`, `arm64`, 256 MB, 30 s timeout |
| Execution role | `lambda-doc-processor-role`: `s3:GetObject` on `mortgages/*`, `dynamodb:PutItem` on the metadata table, its own log group ([IAM matrix](aws-iam-matrix.md)) |
| Who may invoke | `s3.amazonaws.com`, only for source bucket `capstone-mortgage-docs-dev` in this account (resource policy statement `s3-docs-bucket-invoke`) |
| Deploy | `bash scripts/aws/lambda-deploy.sh` (zip package; idempotent) |
| Unit tests | `python3 -m unittest discover -s infrastructure/aws/lambda/doc_processor/tests -v` (9 tests, S3 and DynamoDB faked; run in CI) |
| Live check | `bash scripts/aws/lambda-verify.sh` |

## Validation rules

The function applies the same allowlist as the upload API (`analytics src/api/hardening.py`). That way a file put into the bucket another way, such as by an operator or a future integration, is held to the same rules.

| Check | Rejection reason |
| --- | --- |
| Content-Type is one of `application/pdf`, `image/png`, `image/jpeg`, `text/plain` | `CONTENT_TYPE_NOT_ALLOWED:<type>` |
| Extension matches the type (`.pdf`, `.png`, `.jpg`/`.jpeg`, `.txt`) | `EXTENSION_MISMATCH` |
| Magic bytes match: PDF `%PDF-`, PNG `\x89PNG…`, JPEG `\xff\xd8\xff` | `MAGIC_BYTES_MISMATCH` |
| `text/plain` contains no NUL bytes in the first 1 KB | `BINARY_CONTENT_IN_TEXT` |
| Size is 1 byte to 10 MB | `EMPTY_FILE` / `TOO_LARGE` |

A key outside `mortgages/MTG-nnnn/<file>` is logged at `WARN` and skipped, without being read. The function reads only the first 1 KB (a ranged GET), so the cost and memory are the same for a 10 MB PDF as for a 1 KB one.

## Metadata item (`CapstoneMortgageDocumentMetadata-dev`)

| Attribute | Example | Notes |
| --- | --- | --- |
| **PK** `mortgageExternalId` | `MTG-1002` | All documents of one loan sit in one partition: a `Query` by mortgage returns them |
| **SK** `s3Key` | `mortgages/MTG-1002/ec4f…-deed.pdf` | Unique per upload. S3 can deliver an event twice, and writing the same key again overwrites the same item, so reprocessing is idempotent. |
| `status` | `VALIDATED` / `REJECTED` | |
| `rejectReasons` | `{"MAGIC_BYTES_MISMATCH"}` | String set; only present when rejected |
| `fileName`, `contentType`, `sizeBytes`, `eTag`, `serverSideEncryption` | `deed.pdf`, `application/pdf`, `60`, …, `AES256` | `serverSideEncryption` is also evidence for Task 8.2 |
| `documentType`, `correlationId` | `DEED`, `ddb23919-…` | From the S3 object metadata set by the upload API: ties the item to the API request |
| `uploadedAt`, `processedAt`, `lambdaRequestId` | | |
| `expiresAt` (TTL) | epoch + 30 days | Same 30 days as the bucket's dev lifecycle rule, so an item never outlives its document |

The table uses on-demand capacity, so it has no idle cost. It is encrypted at rest with an AWS-owned key (the DynamoDB default). Table definition: [`infrastructure/aws/dynamodb/document-metadata-table.json`](../../infrastructure/aws/dynamodb/document-metadata-table.json). The Task 8.4 lookup table (`CapstoneMortgageLookup-dev`) is a separate table with a different access pattern.

## Structured logs

Each document produces one line with the `guides/standards.md` fields plus context. No file content, credentials or tokens are logged.

```json
{"timestamp":"2026-11-03T02:10:41.512Z","level":"INFO","service":"doc-processor-lambda","correlationId":"ddb23919-a117-4969-a666-60d8f57a945f","message":"Document validated","mortgageId":"MTG-1002","s3Key":"mortgages/MTG-1002/…-deed.pdf","contentType":"application/pdf","sizeBytes":60,"status":"VALIDATED","documentType":"DEED","lambdaRequestId":"…","durationMs":41.7}
```

Levels:
- `INFO`: validated.
- `WARN`: rejected or skipped. That's a normal outcome, not a failure.
- `ERROR`: S3 or DynamoDB failed. The exception is re-raised.

Search by correlation id:

```bash
aws logs tail /aws/lambda/capstone-mortgage-doc-processor-dev --since 15m --profile capstone-dev
aws logs filter-log-events --profile capstone-dev --log-group-name /aws/lambda/capstone-mortgage-doc-processor-dev \
  --filter-pattern '{ $.correlationId = "ddb23919-a117-4969-a666-60d8f57a945f" }' --query 'events[].message' --output text
```

## Error alarm

`capstone-mortgage-doc-processor-dev-errors`:
- **Fires on:** `AWS/Lambda` `Errors`, Sum ≥ 1 over 5 minutes. Missing data counts as OK.
- **What counts as an error:** only infrastructure failures, raised as exceptions. Rejected documents don't count.
- **Retries:** S3 invokes the function asynchronously, so Lambda retries a failed event twice.

The alarm is a **stub**: it changes state but notifies no one. To wire it up later, in M9 Observability:

```bash
aws sns create-topic --name capstone-mortgage-alerts-dev --profile capstone-dev
aws sns subscribe --topic-arn <topic-arn> --protocol email --notification-endpoint <on-call address> --profile capstone-dev
aws cloudwatch put-metric-alarm ... --alarm-actions <topic-arn>     # re-run lambda-deploy.sh with the action added
```

When the alarm fires:
1. Run `aws logs tail … --since 30m` and look for `"level":"ERROR"`. The `errorType`, `error` and `s3Key` fields say which call failed.
2. If it's a DynamoDB `AccessDenied` or `ResourceNotFound`, check that the table exists and the role policy is applied: `iam-verify.sh`, then `lambda-deploy.sh`.
3. If it's throttling or a timeout, the two retries usually clear it. After that, a failed event is dropped, so reprocess the document with the command below. Production would add an on-failure destination, an SQS DLQ, to the asynchronous invoke config.
4. If it's a code error, fix `handler.py`, run the unit tests, then `lambda-deploy.sh`. Every object that failed can be reprocessed.

Reprocessing (invoking with a synthetic S3 event; the item is overwritten, so it's idempotent):

```bash
aws lambda invoke --profile capstone-dev --function-name capstone-mortgage-doc-processor-dev --cli-binary-format raw-in-base64-out \
  --payload '{"Records":[{"eventName":"ObjectCreated:Put","s3":{"bucket":{"name":"capstone-mortgage-docs-dev"},"object":{"key":"mortgages/MTG-1002/<uuid>-deed.pdf","size":60}}}]}' /dev/stdout
```

## Deploy

```bash
aws login --profile capstone-dev --region us-east-2
bash scripts/aws/lambda-deploy.sh     # table + TTL, log group (7 d), zip + function, S3 permission + notification, alarm
bash scripts/aws/lambda-verify.sh     # live: valid PDF -> VALIDATED, fake PDF -> REJECTED, log lines by correlationId
```

What the deploy script does:
- **Package:** builds the zip with Python's `zipfile`: one file, `handler.py`, with a fixed timestamp so the same code always produces the same zip.
- **Code changes:** if the function already exists, it runs `update-function-code` and then `update-function-configuration`.
- **Teardown:** `scripts/aws/teardown.sh` removes, in this order:
  1. the bucket notification;
  2. the function, the alarm and the log group;
  3. the table;
  4. the buckets and the roles.
