"""Task 6.3: OWASP API Top 10 checks for the analytics service (headers, validation envelope, uploads, throttling)."""
import os

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from src.api.dependencies import get_db
from src.api.hardening import CONTENT_SECURITY_POLICY
from src.api.main import app
from src.api.routes import documents
from tests.conftest import auth_header

client = TestClient(app)


class FakeDatabase:
    def __init__(self):
        self.inserts = []
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((str(query), params))
        sql = str(query)
        if "SELECT id FROM mortgage" in sql:
            found = params["ext_id"] == "MTG-1002"
            return type("Result", (), {"fetchone": lambda self: ("11111111-2222-3333-4444-555555555555",) if found else None})()
        if "FROM payment" in sql:
            return type("Result", (), {"fetchall": lambda self: []})()
        self.inserts.append(params)
        return None

    def commit(self):
        pass


@pytest.fixture
def db():
    fake = FakeDatabase()
    app.dependency_overrides[get_db] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def bucket():
    with mock_aws():
        os.environ["S3_BUCKET_DOCUMENTS"] = "owasp-test-bucket"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="owasp-test-bucket")
        yield s3


def upload(filename="deed.pdf", content=b"%PDF-1.7 test", content_type="application/pdf",
           mortgage="MTG-1002", doc_type="DEED", role="UNDERWRITER", sub="underwriter@capstone.local"):
    return client.post("/api/v1/documents/upload",
                       data={"mortgage_external_id": mortgage, "document_type": doc_type},
                       files={"file": (filename, content, content_type)},
                       headers=auth_header(role, sub=sub))


# --- API8 security misconfiguration: headers ---------------------------------------------------------------

def test_security_headers_on_success_and_error_responses():
    for response in (client.get("/health"), client.get("/api/v1/analytics/portfolio-summary")):
        assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "permissions-policy" in response.headers
        assert "x-correlation-id" in response.headers


# --- validation envelope -----------------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["from=yesterday&to=2026-01-01", "from=2026-02-01&to=2026-01-01",
                                   "from=1990-01-01&to=2026-01-01", "to=2026-01-01"])
def test_payment_trends_rejects_bad_dates_with_400_envelope(db, query):
    response = client.get(f"/api/v1/analytics/payment-trends?{query}", headers=auth_header("RISK_ANALYST"))
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR" and body["correlationId"] and body["timestamp"]


def test_borrower_id_format_is_enforced(db):
    response = client.get("/api/v1/analytics/borrowers/BOR-001' OR '1'='1/risk-summary",
                          headers=auth_header("RISK_ANALYST"))
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# --- API4 unrestricted resource consumption / uploads ------------------------------------------------------

def test_valid_upload_succeeds_with_sanitised_key(db, bucket):
    response = upload(filename="../../etc/my deed.pdf")
    assert response.status_code == 200, response.text
    key = response.json()["s3Key"]
    assert key.startswith("mortgages/MTG-1002/") and key.endswith("-my_deed.pdf") and ".." not in key
    assert db.inserts[0]["file_name"] == "my_deed.pdf"


def test_oversized_upload_is_413(db, bucket, monkeypatch):
    monkeypatch.setattr(documents, "MAX_UPLOAD_BYTES", 16)
    response = upload(content=b"%PDF-" + b"x" * 64)
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_oversized_body_is_rejected_before_parsing(db, bucket, monkeypatch):
    import src.api.main as main
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 1024)   # limit + 64 KB multipart slack, then 413 from middleware
    response = upload(content=b"%PDF-" + b"x" * (200 * 1024))
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
    assert bucket.list_objects_v2(Bucket="owasp-test-bucket").get("KeyCount", 0) == 0


@pytest.mark.parametrize("filename,content,content_type", [
    ("evil.exe", b"MZ\x90\x00", "application/x-msdownload"),
    ("fake.pdf", b"MZ\x90\x00 not a pdf", "application/pdf"),
    ("page.html", b"<script>alert(1)</script>", "text/html"),
])
def test_disallowed_or_spoofed_types_are_415(db, bucket, filename, content, content_type):
    response = upload(filename=filename, content=content, content_type=content_type)
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.parametrize("mortgage,doc_type", [("../../secrets", "DEED"), ("MTG-1002", "deed; DROP TABLE document")])
def test_upload_form_fields_are_validated(db, bucket, mortgage, doc_type):
    response = upload(mortgage=mortgage, doc_type=doc_type)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_mortgage_creates_no_s3_object(db, bucket):
    response = upload(mortgage="MTG-9999")
    assert response.status_code == 404
    assert bucket.list_objects_v2(Bucket="owasp-test-bucket").get("KeyCount", 0) == 0


def test_uploads_are_rate_limited_per_user(db, bucket, monkeypatch):
    monkeypatch.setattr(documents, "UPLOADS_PER_USER_PER_MINUTE", 2)
    assert upload(sub="busy@capstone.local").status_code == 200
    assert upload(sub="busy@capstone.local").status_code == 200
    third = upload(sub="busy@capstone.local")
    assert third.status_code == 429
    assert third.json()["code"] == "RATE_LIMITED" and int(third.headers["retry-after"]) >= 1
    assert upload(sub="someone-else@capstone.local").status_code == 200


def test_storage_errors_do_not_leak_internals(db, monkeypatch):
    from botocore.exceptions import ClientError
    from src.services import s3_service

    class BrokenClient:
        def put_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchBucket", "Message": "bucket secret-internal-bucket"}}, "PutObject")

    monkeypatch.setattr(s3_service, "get_s3_client", lambda: BrokenClient())
    response = upload()
    assert response.status_code == 502
    assert "secret-internal-bucket" not in response.text and "NoSuchBucket" not in response.text
