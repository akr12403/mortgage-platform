import pytest
from moto import mock_aws
import boto3
from fastapi.testclient import TestClient
from src.api.main import app

@mock_aws
def test_document_upload_s3():
    # 1. Setup mock S3 bucket
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket-documents")

    client = TestClient(app)

    # 2. Perform test upload request
    response = client.post(
        "/api/v1/documents/upload",
        data={"mortgage_external_id": "MTG-1002", "document_type": "DEED"},
        files={"file": ("test_deed.txt", b"Mock file content", "text/plain")}
    )

    # 3. Verify success or mock response handling
    assert response.status_code in [200, 201]