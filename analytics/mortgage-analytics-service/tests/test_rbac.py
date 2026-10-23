"""M6 Tasks 6.1/6.2 for the analytics service: JWT validation + role matrix for all five roles."""
import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.main import app
from tests.conftest import auth_header, make_token

ALL_ROLES = ("ADMIN", "UNDERWRITER", "SERVICING_AGENT", "RISK_ANALYST", "SUPPORT")
ANALYTICS_READ = {"ADMIN", "UNDERWRITER", "RISK_ANALYST"}
DOCUMENT_UPLOAD = {"ADMIN", "UNDERWRITER", "SERVICING_AGENT"}

client = TestClient(app)


class _Row:
    _mapping = {"total_mortgages": 1, "active_mortgages": 1, "delinquent_mortgages": 0,
                "outstanding_balance_total": 1.0, "delinquency_rate": 0.0}


class _Result:
    def fetchone(self):
        return _Row()

    def fetchall(self):
        return []


class FakeDatabase:
    def execute(self, query, params=None):
        return _Result()


@pytest.fixture(autouse=True)
def fake_db():
    app.dependency_overrides[get_db] = lambda: FakeDatabase()
    yield
    app.dependency_overrides.clear()


READ_ENDPOINTS = [
    "/api/v1/analytics/portfolio-summary",
    "/api/v1/analytics/delinquency",
    "/api/v1/analytics/payment-trends?from=2025-01-01&to=2026-12-31",
    "/api/v1/analytics/event-stats",
]


@pytest.mark.parametrize("path", READ_ENDPOINTS)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_analytics_read_matrix(path, role):
    response = client.get(path, headers=auth_header(role))
    if role in ANALYTICS_READ:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403
        assert response.json()["code"] == "ACCESS_DENIED"
        assert response.json()["correlationId"] == response.headers["x-correlation-id"]


@pytest.mark.parametrize("role", ALL_ROLES)
def test_document_upload_matrix(role):
    # Forbidden roles are rejected before the upload is processed; allowed roles get past auth
    # (the request is then intentionally incomplete, so validation answers 422).
    response = client.post("/api/v1/documents/upload", headers=auth_header(role))
    if role in DOCUMENT_UPLOAD:
        assert response.status_code == 422
    else:
        assert response.status_code == 403
        assert response.json()["code"] == "ACCESS_DENIED"


def test_missing_token_is_401_with_envelope():
    response = client.get("/api/v1/analytics/portfolio-summary")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("token", [
    make_token(expires_in=-120),                                   # expired (beyond 30 s leeway)
    make_token(secret="attacker-controlled-secret-0123456789-xyz"),  # wrong key
    make_token(issuer="evil-issuer"),                              # wrong issuer
    "not-a-jwt",
])
def test_invalid_tokens_are_401(token):
    response = client.get("/api/v1/analytics/portfolio-summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


def test_alg_none_token_is_rejected():
    import jwt
    unsigned = jwt.encode({"sub": "attacker", "roles": ["ADMIN"], "iss": "capstone-mortgage-auth", "exp": 4102444800},
                          key=None, algorithm="none")
    response = client.get("/api/v1/analytics/portfolio-summary", headers={"Authorization": f"Bearer {unsigned}"})
    assert response.status_code == 401


def test_token_without_roles_is_403():
    response = client.get("/api/v1/analytics/portfolio-summary", headers=auth_header("GUEST"))
    assert response.status_code == 403


def test_health_stays_public():
    assert client.get("/health").status_code == 200
