import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import os
import uuid
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def get_s3_client():
    """S3 client for document uploads.

    S3_ENDPOINT_URL lets S3 go somewhere other than the rest of the AWS traffic: docker-compose.aws.yml sets it to ""
    (real S3 in the sandbox Region) while SQS keeps using LocalStack through AWS_ENDPOINT_URL. Unset, it falls back to
    AWS_ENDPOINT_URL (LocalStack/Moto), as before. Credentials come from the default chain only: in the AWS mode they
    are short-lived STS credentials for mortgage-analytics-role (scripts/aws/compose-aws-up.sh), never static keys.
    """
    s3_endpoint = os.getenv("S3_ENDPOINT_URL")
    endpoint_url = (os.getenv("AWS_ENDPOINT_URL", "") if s3_endpoint is None else s3_endpoint) or None
    region = os.getenv("S3_REGION") or os.getenv("AWS_REGION") or None
    config = Config(
        retries={'max_attempts': 3},
        connect_timeout=5,
        read_timeout=10,
        # boto3 itself also reads AWS_ENDPOINT_URL from the environment; S3_ENDPOINT_URL="" must beat that.
        ignore_configured_endpoint_urls=(s3_endpoint == ""),
    )
    return boto3.client('s3', config=config, endpoint_url=endpoint_url, region_name=region)

def upload_document_to_s3(file_bytes: bytes, mortgage_external_id: str, file_name: str, correlation_id: str = None,
                          content_type: str = "application/octet-stream") -> str:
    bucket_name = os.getenv("S3_BUCKET_DOCUMENTS", "capstone-mortgage-docs-dev")
    unique_filename = f"{uuid.uuid4()}-{file_name}"
    s3_key = f"mortgages/{mortgage_external_id}/{unique_filename}"
    
    s3_client = get_s3_client()
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
            ServerSideEncryption="AES256",  # the bucket default is SSE-S3 too; explicit so it holds on any bucket
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