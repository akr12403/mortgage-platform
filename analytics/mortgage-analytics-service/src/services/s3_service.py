import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import os
import uuid
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def get_s3_client():
    endpoint_url = os.getenv("AWS_ENDPOINT_URL")  # LocalStack / Moto endpoint if applicable
    config = Config(
        retries={'max_attempts': 3},
        connect_timeout=5,
        read_timeout=10
    )
    return boto3.client('s3', config=config, endpoint_url=endpoint_url)

def upload_document_to_s3(file_bytes: bytes, mortgage_external_id: str, file_name: str, correlation_id: str = None,
                          content_type: str = "application/octet-stream") -> str:
    bucket_name = os.getenv("S3_BUCKET_DOCUMENTS", "mortgage-documents-dev")
    unique_filename = f"{uuid.uuid4()}-{file_name}"
    s3_key = f"mortgages/{mortgage_external_id}/{unique_filename}"
    
    s3_client = get_s3_client()
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
        )
        logger.info(f"[{correlation_id}] Successfully uploaded {s3_key} to S3 bucket {bucket_name}")
        return s3_key
    except (BotoCoreError, ClientError) as e:
        # Full detail stays in the log; the client gets a generic message (no bucket names or AWS internals).
        logger.error(f"[{correlation_id}] S3 upload failed: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "S3_UPLOAD_ERROR",
                "message": "Document storage is temporarily unavailable",
                "correlationId": correlation_id
            }
        )