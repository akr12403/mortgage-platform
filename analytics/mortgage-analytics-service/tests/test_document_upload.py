import os

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws

from src.api.dependencies import get_db
from src.api.main import app


class FakeDatabase:
    """Stands in for the SQLAlchemy session so the test needs no running PostgreSQL."""

    def __init__(self):
        self.inserts = []
        self.committed = False

    def execute(self, query, params=None):
        sql = str(query)
        if "SELECT id FROM mortgage" in sql:
            mortgage_id = "11111111-2222-3333-4444-555555555555" if params["ext_id"] == "MTG-1002" else None
            return type("Result", (), {"fetchone": lambda self: (mortgage_id,) if mortgage_id else None})()
        self.inserts.append(params)
        return None

    def commit(self):
        self.committed = True


@mock_aws
def test_document_upload_s3():
    os.environ["S3_BUCKET_DOCUMENTS"] = "my-documents-bucket"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="my-documents-bucket")

    db = FakeDatabase()
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).post(
            "/api/v1/documents/upload",
            data={"mortgage_external_id": "MTG-1002", "document_type": "DEED"},
            files={"file": ("test_deed.txt", b"Mock file content", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code in [200, 201]
    body = response.json()
    assert body["mortgageExternalId"] == "MTG-1002"
    assert body["s3Key"].startswith("mortgages/MTG-1002/")
    assert db.committed and db.inserts[0]["file_name"] == "test_deed.txt"
    stored = s3.get_object(Bucket="my-documents-bucket", Key=body["s3Key"])["Body"].read()
    assert stored == b"Mock file content"
