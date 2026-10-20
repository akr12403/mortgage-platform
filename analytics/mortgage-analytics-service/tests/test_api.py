import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.dependencies import get_db

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"
    assert data["service"] == "mortgage-analytics-service"

def test_get_portfolio_summary():
    class Result:
        def fetchone(self):
            return type("Row", (), {"_mapping": {
                "total_mortgages": 12,
                "active_mortgages": 10,
                "delinquent_mortgages": 2,
                "outstanding_balance_total": 3842500.0,
                "delinquency_rate": 0.2
            }})()

    class FakeDatabase:
        def execute(self, query):
            return Result()

    def override_get_db():
        yield FakeDatabase()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/api/v1/analytics/portfolio-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "totalMortgages": 12,
        "activeMortgages": 10,
        "delinquentMortgages": 2,
        "outstandingBalanceTotal": 3842500.0,
        "delinquencyRate": 0.2,
        "asOf": response.json()["asOf"]
    }
    assert response.json()["asOf"].endswith("+00:00")


def test_payment_trends_contract():
    class FakeDatabase:
        def execute(self, query, params):
            row = type("Row", (), {"_mapping": {
                "period": "2026-01",
                "posted_amount": 22000.0,
                "on_time_rate": 0.95
            }})()
            return type("Result", (), {"fetchall": lambda self: [row]})()

    def override_get_db():
        yield FakeDatabase()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get(
            "/api/v1/analytics/payment-trends",
            params={"from": "2025-01-01", "to": "2026-12-31"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "from": "2025-01-01",
        "to": "2026-12-31",
        "buckets": [{
            "period": "2026-01",
            "postedAmount": 22000.0,
            "onTimeRate": 0.95
        }]
    }


def test_http_error_uses_shared_error_envelope():
    response = client.get("/api/v1/analytics/borrowers/BOR-999/risk-summary")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["correlationId"] == response.headers["x-correlation-id"]
    assert response.json()["timestamp"].endswith("+00:00")