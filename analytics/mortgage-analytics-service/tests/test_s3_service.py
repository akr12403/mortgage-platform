"""M8 Task 8.2: the document S3 client can target real S3 while SQS stays on LocalStack, and uploads ask for SSE-S3."""
import boto3
import pytest
from moto import mock_aws

from src.services import s3_service


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL", "S3_REGION", "AWS_REGION", "S3_BUCKET_DOCUMENTS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def _endpoint(client):
    return client.meta.endpoint_url


def test_falls_back_to_aws_endpoint_url_for_localstack(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localstack:4566")
    assert _endpoint(s3_service.get_s3_client()) == "http://localstack:4566"


def test_empty_s3_endpoint_means_real_s3_even_when_localstack_is_set(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localstack:4566")  # SQS keeps using LocalStack
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("S3_REGION", "us-east-2")
    client = s3_service.get_s3_client()
    assert client.meta.region_name == "us-east-2"
    assert _endpoint(client) == "https://s3.us-east-2.amazonaws.com"


def test_s3_region_overrides_aws_region(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("S3_REGION", "us-east-2")
    assert s3_service.get_s3_client().meta.region_name == "us-east-2"


@mock_aws
def test_upload_uses_default_bucket_name_and_requests_sse_s3():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="capstone-mortgage-docs-dev")
    key = s3_service.upload_document_to_s3(b"hello", "MTG-1002", "note.txt", "cid-1", content_type="text/plain")
    assert key.startswith("mortgages/MTG-1002/") and key.endswith("-note.txt")
    head = s3.head_object(Bucket="capstone-mortgage-docs-dev", Key=key)
    assert head["ServerSideEncryption"] == "AES256"
    assert head["ContentType"] == "text/plain"
