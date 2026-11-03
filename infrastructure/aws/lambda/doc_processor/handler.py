"""M8 Task 8.3: document processor Lambda (capstone-mortgage-doc-processor-dev).

Trigger: s3:ObjectCreated:* on s3://capstone-mortgage-docs-dev/mortgages/ (one record per uploaded object).
For each object it:
  1. reads only the first bytes (ranged GET) and validates the file type: extension, declared Content-Type,
     magic bytes, size; text/plain must not contain NUL bytes;
  2. writes ONE metadata item to DynamoDB CapstoneMortgageDocumentMetadata-dev
     (PK mortgageExternalId, SK s3Key; status VALIDATED or REJECTED with reasons; TTL matches the 30-day lifecycle);
  3. logs one structured JSON line (guides/standards.md fields) to CloudWatch Logs.

Rejected files are a normal outcome (logged at WARN, status REJECTED). Infrastructure failures (S3/DynamoDB errors)
are logged at ERROR and re-raised, so the invocation counts in the Lambda Errors metric that the alarm watches and
S3's asynchronous invocation retries it. Writing the same (mortgageExternalId, s3Key) again is idempotent.

IAM (lambda-doc-processor-role): s3:GetObject on mortgages/*, dynamodb:PutItem on the metadata table, its own logs.
No file content and no secrets are ever logged. Standard library + boto3 (included in the Lambda runtime) only.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import unquote_plus

SERVICE = "doc-processor-lambda"
UPLOAD_PREFIX = os.getenv("DOCS_UPLOAD_PREFIX", "mortgages/")
TABLE = os.getenv("DOC_METADATA_TABLE", "CapstoneMortgageDocumentMetadata-dev")
MAX_BYTES = int(os.getenv("MAX_DOCUMENT_BYTES", str(10 * 1024 * 1024)))  # same 10 MB limit as the upload API
RETENTION_DAYS = int(os.getenv("METADATA_RETENTION_DAYS", "30"))
SNIFF_BYTES = 1024

# Same allowlist as the upload API (analytics src/api/hardening.py), so a file that skipped the API is held to the
# same rules.
ALLOWED = {
    "application/pdf": {"extensions": (".pdf",), "magic": (b"%PDF-",)},
    "image/png": {"extensions": (".png",), "magic": (b"\x89PNG\r\n\x1a\n",)},
    "image/jpeg": {"extensions": (".jpg", ".jpeg"), "magic": (b"\xff\xd8\xff",)},
    "text/plain": {"extensions": (".txt",), "magic": ()},
}
KEY_PATTERN = re.compile(r"^" + re.escape(UPLOAD_PREFIX) + r"(MTG-\d{4,10})/([^/]+)$")

_clients = {}


def _client(name):
    if name not in _clients:
        import boto3  # in the Lambda runtime; imported lazily so the unit tests need no AWS libraries
        _clients[name] = boto3.client(name)
    return _clients[name]


def log(level, message, correlation_id, **fields):
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": level,
        "service": SERVICE,
        "correlationId": correlation_id,
        "message": message,
        **{k: v for k, v in fields.items() if v is not None},
    }
    print(json.dumps(record, separators=(",", ":"), sort_keys=False), flush=True)


def validate(file_name, content_type, size, head):
    """Return a list of rejection reasons (empty list = valid)."""
    reasons = []
    rule = ALLOWED.get(content_type)
    if rule is None:
        return [f"CONTENT_TYPE_NOT_ALLOWED:{content_type or 'missing'}"]
    if not file_name.lower().endswith(rule["extensions"]):
        reasons.append("EXTENSION_MISMATCH")
    if rule["magic"] and not head.startswith(rule["magic"]):
        reasons.append("MAGIC_BYTES_MISMATCH")
    if content_type == "text/plain" and b"\x00" in head:
        reasons.append("BINARY_CONTENT_IN_TEXT")
    if size == 0:
        reasons.append("EMPTY_FILE")
    if size > MAX_BYTES:
        reasons.append("TOO_LARGE")
    return reasons


def process_record(record, request_id):
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])  # S3 event keys are URL-encoded
    size = int(record["s3"]["object"].get("size", 0))
    match = KEY_PATTERN.match(key)
    if not match:
        log("WARN", "Object outside the expected layout; skipped", request_id, s3Key=key, bucket=bucket)
        return {"s3Key": key, "status": "SKIPPED"}
    mortgage_id, stored_name = match.groups()
    file_name = re.sub(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-", "", stored_name)

    started = time.monotonic()
    ranged = {"Range": f"bytes=0-{SNIFF_BYTES - 1}"} if size > 0 else {}  # a Range on an empty object is a 416
    obj = _client("s3").get_object(Bucket=bucket, Key=key, **ranged)
    head = obj["Body"].read(SNIFF_BYTES)
    content_type = (obj.get("ContentType") or "").split(";", 1)[0].strip().lower()
    correlation_id = (obj.get("Metadata") or {}).get("correlation-id") or request_id
    document_type = (obj.get("Metadata") or {}).get("document-type")

    reasons = validate(file_name, content_type, size, head)
    status = "REJECTED" if reasons else "VALIDATED"
    now = datetime.now(timezone.utc)
    item = {
        "mortgageExternalId": {"S": mortgage_id},
        "s3Key": {"S": key},
        "bucket": {"S": bucket},
        "fileName": {"S": file_name},
        "contentType": {"S": content_type or "missing"},
        "sizeBytes": {"N": str(size)},
        "status": {"S": status},
        "serverSideEncryption": {"S": obj.get("ServerSideEncryption") or "NONE"},
        "eTag": {"S": (record["s3"]["object"].get("eTag") or "").strip('"')},
        "uploadedAt": {"S": record.get("eventTime", now.isoformat())},
        "processedAt": {"S": now.isoformat(timespec="seconds")},
        "correlationId": {"S": correlation_id},
        "lambdaRequestId": {"S": request_id},
        "expiresAt": {"N": str(int(now.timestamp()) + RETENTION_DAYS * 86400)},
    }
    if document_type:
        item["documentType"] = {"S": document_type}
    if reasons:
        item["rejectReasons"] = {"SS": reasons}
    _client("dynamodb").put_item(TableName=TABLE, Item=item)

    log("WARN" if reasons else "INFO",
        "Document rejected" if reasons else "Document validated",
        correlation_id, mortgageId=mortgage_id, s3Key=key, contentType=content_type or "missing", sizeBytes=size,
        status=status, rejectReasons=reasons or None, documentType=document_type, lambdaRequestId=request_id,
        durationMs=round((time.monotonic() - started) * 1000, 1))
    return {"s3Key": key, "status": status, "reasons": reasons}


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", "local")
    results = []
    for record in event.get("Records", []):
        if not str(record.get("eventName", "")).startswith("ObjectCreated"):
            continue
        try:
            results.append(process_record(record, request_id))
        except Exception as exc:  # infrastructure failure: log, then fail the invocation (Errors metric -> alarm)
            log("ERROR", "Document processing failed", request_id,
                s3Key=unquote_plus(record.get("s3", {}).get("object", {}).get("key", "")),
                errorType=type(exc).__name__, error=str(exc)[:300])
            raise
    return {"processed": len(results), "results": results}
