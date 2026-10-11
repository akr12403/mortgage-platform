import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"
    assert data["service"] == "mortgage-analytics-service"

def test_get_portfolio_summary():
    response = client.get("/api/v1/analytics/summary")
    assert response.status_code in [200, 404]