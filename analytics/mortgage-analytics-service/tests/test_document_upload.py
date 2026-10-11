import os
import pytest
from moto import mock_aws
import boto3
from fastapi.testclient import TestClient
from src.api.main import app

@mock_aws
def test_document_upload_s3():
    # Set expected environment variable if needed
    os.environ["S3_BUCKET_DOCUMENTS"] = "my-documents-bucket"
    
    # Setup mock S3 bucket matching the config
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="my-documents-bucket")

    client = TestClient(app)

    response = client.post(
        "/api/v1/documents/upload",
        data={"mortgage_external_id": "MTG-1002", "document_type": "DEED"},
        files={"file": ("test_deed.txt", b"Mock file content", "text/plain")}
    )

    assert response.status_code in [200, 201]