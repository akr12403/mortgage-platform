"""M8 Task 8.5: the analytics service reads the Glue-curated delinquency report from S3 (Moto)."""
import json

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from src.api.main import app
from src.api.routes.curated import get_curated_reader
from src.services.curated_report import CuratedReportReader
from tests.conftest import auth_header

BUCKET, PREFIX = "capstone-mortgage-analytics-dev", "curated/delinquency_report/"
HEADER = ("report_date,mortgage_external_id,borrower_external_id,status,original_amount,outstanding_balance,"
          "is_delinquent,days_past_due,delinquency_severity,delinquent_since,risk_bucket,last_payment_date,"
          "posted_payment_total")
ROWS = [
    "2026-11-04,MTG-1001,BOR-001,ACTIVE,310000.00,304999.96,false,0,NONE,,CURRENT,2026-11-02,3700.00",
    "2026-11-04,MTG-1002,BOR-002,DELINQUENT,280000.00,277150.00,true,95,CRITICAL,2026-08-01,DPD_90_PLUS,2026-11-03,1850.00",
    "2026-11-04,MTG-1005,BOR-004,DELINQUENT,200000.00,198000.00,true,33,MODERATE,2026-10-01,DPD_30_59,,0.00",
]


def put_partition(s3, day, rows, header=HEADER):
    base = f"{PREFIX}date={day}/"
    s3.put_object(Bucket=BUCKET, Key=f"{base}part-0000.csv", Body="\n".join([header] + rows) + "\n")
    s3.put_object(Bucket=BUCKET, Key=f"{base}_manifest.json", Body=json.dumps({
        "dataset": "delinquency_report", "schemaVersion": 1, "reportDate": day, "rowCount": len(rows),
        "files": [f"{base}part-0000.csv"], "pipelineRunId": "pr-abc", "generatedAt": f"{day}T01:00:00+00:00"}))


@pytest.fixture
def client():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        put_partition(s3, "2026-11-03", ROWS[:1])
        put_partition(s3, "2026-11-04", ROWS)
        app.dependency_overrides[get_curated_reader] = lambda: CuratedReportReader(s3, BUCKET, PREFIX)
        yield TestClient(app), s3
        app.dependency_overrides.clear()


def test_latest_partition_summary(client):
    api, _ = client
    body = api.get("/api/v1/analytics/curated/delinquency-report", headers=auth_header("RISK_ANALYST")).json()
    assert body["reportDate"] == "2026-11-04"
    assert (body["mortgageCount"], body["delinquentCount"]) == (3, 2)
    assert body["outstandingBalanceTotal"] == pytest.approx(780149.96)
    assert body["balanceAtRisk"] == pytest.approx(475150.00)
    assert body["byRiskBucket"]["DPD_90_PLUS"] == {"count": 1, "outstandingBalance": 277150.0}
    assert body["byRiskBucket"]["DPD_60_89"]["count"] == 0
    assert body["bySeverity"] == {"CRITICAL": 1, "MODERATE": 1}
    assert [m["mortgageExternalId"] for m in body["mostPastDue"]] == ["MTG-1002", "MTG-1005"]
    assert body["source"]["location"].endswith("date=2026-11-04/part-0000.csv")
    assert body["source"]["pipelineRunId"] == "pr-abc"


def test_specific_date_and_available_dates(client):
    api, _ = client
    assert api.get("/api/v1/analytics/curated/delinquency-report?date=2026-11-03",
                   headers=auth_header("ADMIN")).json()["mortgageCount"] == 1
    assert api.get("/api/v1/analytics/curated/delinquency-report/dates",
                   headers=auth_header("ADMIN")).json() == {"dates": ["2026-11-03", "2026-11-04"]}


def test_missing_partition_bad_date_and_rbac(client):
    api, _ = client
    missing = api.get("/api/v1/analytics/curated/delinquency-report?date=2020-01-01", headers=auth_header("ADMIN"))
    assert missing.status_code == 404 and missing.json()["code"] == "NOT_FOUND"
    assert api.get("/api/v1/analytics/curated/delinquency-report?date=04-11-2026",
                   headers=auth_header("ADMIN")).status_code == 400
    assert api.get("/api/v1/analytics/curated/delinquency-report", headers=auth_header("SERVICING_AGENT")).status_code == 403
    assert api.get("/api/v1/analytics/curated/delinquency-report").status_code == 401


def test_schema_drift_in_curated_file_is_reported_not_crashed(client):
    api, s3 = client
    put_partition(s3, "2026-11-05", [r.replace(",true,", ",yes,") for r in ROWS[:1]],
                  header=HEADER.replace("risk_bucket", "bucket"))
    response = api.get("/api/v1/analytics/curated/delinquency-report?date=2026-11-05", headers=auth_header("ADMIN"))
    assert response.status_code == 502 and response.json()["code"] == "CURATED_SCHEMA_MISMATCH"


def test_s3_failure_is_503():
    class Broken:
        def list_objects_v2(self, **kwargs):
            raise RuntimeError("no credentials")
    app.dependency_overrides[get_curated_reader] = lambda: CuratedReportReader(Broken(), BUCKET, PREFIX)
    try:
        response = TestClient(app).get("/api/v1/analytics/curated/delinquency-report", headers=auth_header("ADMIN"))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503 and response.json()["code"] == "CURATED_UNAVAILABLE"
