"""M9 Task 9.3: JSON logs with correlationId on every line, and one http_request line per request
(contract: docs/operations/observability.md)."""
import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.observability import JsonFormatter, correlation_id_var
from tests.conftest import make_token
from tests.test_event_consumer import envelope, make_processor

CID = "test-corr-0123456789"


@pytest.fixture
def log_lines():
    """Every log record of the test, formatted exactly as in production."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("mortgage-analytics-service"))
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


def http_lines(lines):
    return [line for line in lines if line["message"] == "http_request"]


def test_request_line_has_route_template_status_duration_and_correlation_id(log_lines):
    client = TestClient(app)
    response = client.get("/api/v1/analytics/borrowers/BRW-1001/risk-summary", headers={"X-Correlation-Id": CID})
    assert response.status_code == 401
    (line,) = http_lines(log_lines())
    assert line["service.name"] == "mortgage-analytics-service"
    assert line["log.level"] == "INFO"
    assert line["correlationId"] == CID
    assert line["http.method"] == "GET"
    assert line["http.route"] == "/api/v1/analytics/borrowers/{borrower_external_id}/risk-summary"  # never the id
    assert line["http.status"] == 401
    assert isinstance(line["durationMs"], (int, float)) and line["durationMs"] >= 0
    assert line["@timestamp"].endswith("Z")


def test_unknown_path_is_logged_as_unmatched_not_raw(log_lines):
    TestClient(app).get("/api/v1/nothing/MTG-1001")
    (line,) = http_lines(log_lines())
    assert line["http.route"] == "unmatched"
    assert line["http.status"] == 404
    assert "MTG-1001" not in json.dumps(line)


def test_health_checks_are_not_request_traffic(log_lines):
    TestClient(app).get("/health")
    assert http_lines(log_lines()) == []


def test_tokens_and_headers_never_reach_the_logs(log_lines):
    token = make_token(("RISK_ANALYST",), expires_in=-60)  # rejected before any database access
    TestClient(app).get("/api/v1/analytics/portfolio-summary?ssn=123-45-6789",
                        headers={"Authorization": f"Bearer {token}", "X-Correlation-Id": CID})
    text = json.dumps(log_lines())
    assert token not in text and "Bearer" not in text and "123-45-6789" not in text


def test_event_handling_logs_carry_the_events_correlation_id(log_lines):
    processor, _ = make_processor()
    body = envelope()
    event = json.loads(body)
    processor.handle(body)
    processed = [line for line in log_lines() if line["message"].startswith("Processed")]
    assert processed and processed[0]["correlationId"] == event["correlationId"]
    assert processed[0]["eventId"] == event["eventId"]
    assert correlation_id_var.get() is None  # reset after the event


def test_formatter_uses_the_java_level_names_and_ecs_error_fields():
    formatter = JsonFormatter("svc")
    warn = logging.LogRecord("x", logging.WARNING, __file__, 1, "careful", (), None)
    assert json.loads(formatter.format(warn))["log.level"] == "WARN"
    try:
        raise ValueError("bad input")
    except ValueError:
        import sys
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    doc = json.loads(formatter.format(record))
    assert doc["error.type"] == "ValueError" and doc["error.message"] == "bad input"
    assert "Traceback" in doc["error.stack_trace"]
