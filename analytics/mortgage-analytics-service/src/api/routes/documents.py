import uuid
from fastapi import APIRouter, Depends, File, Form, UploadFile, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from src.api.dependencies import get_db
from src.services.s3_service import upload_document_to_s3

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

@router.post("/upload")
async def upload_document(
    request: Request,
    mortgage_external_id: str = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    correlation_id = getattr(request.state, "correlation_id", None)
    
    # Read file contents
    file_bytes = await file.read()
    original_filename = file.filename or "unnamed_file"
    
    # 1. Upload to S3 with retries and timeout error handling
    s3_key = upload_document_to_s3(file_bytes, mortgage_external_id, original_filename, correlation_id)
    
    # 2. Look up internal mortgage id using mortgage_external_id
    mortgage_res = db.execute(
        text("SELECT id FROM mortgage WHERE mortgage_external_id = :ext_id"),
        {"ext_id": mortgage_external_id}
    ).fetchone()
    
    if not mortgage_res:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": f"Mortgage {mortgage_external_id} not found",
                "correlationId": correlation_id
            }
        )
    mortgage_id = mortgage_res[0]
    
    # 3. Insert row into document table with s3_key
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
            "file_name": original_filename
        }
    )
    db.commit()
    
    return {
        "documentId": doc_id,
        "mortgageExternalId": mortgage_external_id,
        "s3Key": s3_key,
        "status": "UPLOADED"
    }