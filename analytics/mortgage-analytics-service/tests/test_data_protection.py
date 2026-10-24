"""M6 Task 6.6 regression tests for the data-protection findings DP-GAP-1 and DP-GAP-2."""
import pytest
from fastapi.testclient import TestClient

from src.api import dependencies
from src.api.dependencies import get_db
from src.api.main import app
from tests.conftest import auth_header

client = TestClient(app)

ROW = {
    "borrower_external_id": "BOR-001",
    "first_name": "Alex",
    "last_name": "Rivera",
    "total_mortgages": 2,
    "total_outstanding_balance": 610000.0,
    "delinquent_count": 1,
}


class FakeDatabase:
    def execute(self, query, params=None):
        row = type("Row", (), {"_mapping": ROW})()
        return type("Result", (), {"fetchone": lambda self: row})()


@pytest.fixture
def db():
    app.dependency_overrides[get_db] = lambda: FakeDatabase()
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["ADMIN", "UNDERWRITER"])
def test_pii_roles_see_borrower_names(db, role):
    body = client.get("/api/v1/analytics/borrowers/BOR-001/risk-summary", headers=auth_header(role)).json()
    assert body["firstName"] == "Alex" and body["lastName"] == "Rivera"


def test_risk_analyst_gets_aggregates_without_names(db):
    """DP-GAP-1: RISK_ANALYST has no borrower-PII access (security-controls.md), so names are omitted."""
    response = client.get("/api/v1/analytics/borrowers/BOR-001/risk-summary", headers=auth_header("RISK_ANALYST"))
    assert response.status_code == 200
    body = response.json()
    assert "firstName" not in body and "lastName" not in body
    assert "Alex" not in response.text and "Rivera" not in response.text
    assert body["borrowerExternalId"] == "BOR-001"
    assert body["totalOutstandingBalance"] == 610000.0 and body["delinquentCount"] == 1


def test_missing_db_password_fails_fast(monkeypatch):
    """DP-GAP-2: no default DB password; startup refuses to run without one."""
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        dependencies.validate_db_settings()
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    dependencies.validate_db_settings()


def test_db_url_escapes_special_characters():
    from sqlalchemy.engine import URL
    url = URL.create("postgresql+psycopg2", username="u", password="p@ss:w/rd", host="h", port=5432, database="d")
    assert url.password == "p@ss:w/rd"
    assert "p@ss:w/rd" not in url.render_as_string(hide_password=True)
