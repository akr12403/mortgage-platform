import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from src.api.dependencies import get_db
from src.services.s3_service import upload_document_to_s3
from src.api.security import DOCUMENT_UPLOAD, require_roles
from src.api.hardening import (ALLOWED_CONTENT_TYPES, RateLimiter, content_matches_type, sanitize_filename)

# RBAC (M6 Task 6.2): document upload requires ADMIN, UNDERWRITER or SERVICING_AGENT.
router = APIRouter(prefix="/api/v1/documents", tags=["documents"],
                   dependencies=[Depends(require_roles(*DOCUMENT_UPLOAD))])

# Task 6.3 (OWASP API4 unrestricted resource consumption): bounded size, type allowlist, per-user rate limit.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOADS_PER_USER_PER_MINUTE = int(os.getenv("RATE_LIMIT_UPLOADS_PER_USER", "20"))
upload_rate_limiter = RateLimiter()


def _error(request: Request, status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status, headers=headers, detail={
        "code": code,
        "message": message,
        "correlationId": getattr(request.state, "correlation_id", None),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/upload")
async def upload_document(
    request: Request,
    mortgage_external_id: str = Form(..., pattern=r"^MTG-\d{4}$"),
    document_type: str = Form(..., pattern=r"^[A-Z][A-Z_]{1,39}$"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    correlation_id = getattr(request.state, "correlation_id", None)

    # 0. Throttle per authenticated user (set by the RBAC dependency)
    user = getattr(request.state, "user", "unknown")
    decision = upload_rate_limiter.try_acquire(f"upload:{user}", UPLOADS_PER_USER_PER_MINUTE, 60)
    if not decision.allowed:
        raise _error(request, 429, "RATE_LIMITED", "Too many requests; retry later",
                     {"Retry-After": str(decision.retry_after_seconds)})

    # 1. Bounded read, type allowlist + magic bytes, safe filename
    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise _error(request, 413, "PAYLOAD_TOO_LARGE", f"Uploads are limited to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if not file_bytes:
        raise _error(request, 400, "VALIDATION_ERROR", "file: must not be empty")
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if not content_matches_type(content_type, file_bytes):
        raise _error(request, 415, "UNSUPPORTED_MEDIA_TYPE",
                     "Allowed file types: " + ", ".join(sorted(ALLOWED_CONTENT_TYPES)))
    safe_filename = sanitize_filename(file.filename)

    # 2. Look up the mortgage first, so unknown IDs never create S3 objects (parameterised query)
    mortgage_res = db.execute(
        text("SELECT id FROM mortgage WHERE mortgage_external_id = :ext_id"),
        {"ext_id": mortgage_external_id}
    ).fetchone()
    if not mortgage_res:
        raise _error(request, 404, "NOT_FOUND", f"Mortgage {mortgage_external_id} not found")
    mortgage_id = mortgage_res[0]

    # 3. Upload to S3 (retries + timeouts in s3_service); the key only contains validated parts
    s3_key = upload_document_to_s3(file_bytes, mortgage_external_id, safe_filename, correlation_id,
                                   content_type=content_type, document_type=document_type)

    # 4. Insert row into document table with s3_key
    doc_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO document (id, mortgage_id, document_type, s3_key, file_name, created_at)
            VALUES (:id, :mortgage_id, :doc_type, :s3_key, :file_name, NOW())
        """),
        {
            "id": doc_id,
            "mortgage_id": mortgage_id,
            "doc_type": document_type,
            "s3_key": s3_key,
            "file_name": safe_filename
        }
    )
    db.commit()

    return {
        "documentId": doc_id,
        "mortgageExternalId": mortgage_external_id,
        "s3Key": s3_key,
        "status": "UPLOADED"
    }
