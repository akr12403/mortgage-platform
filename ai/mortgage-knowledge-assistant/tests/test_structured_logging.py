"""M9 Task 9.3: JSON logs with correlationId on every line, and one http_request line per request
(contract: docs/operations/observability.md). The formatter itself is unit-tested in the analytics service; the two
copies of src/observability.py are kept identical by tests/contract/test_log_schema.py."""
import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.observability import JsonFormatter

CID = "test-corr-0123456789"


@pytest.fixture
def log_lines():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(main.SERVICE_NAME))
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


def test_request_line_for_the_ask_endpoint(log_lines):
    response = TestClient(main.app).post(main.ASK_PATH, json={"question": "x"}, headers={"X-Correlation-Id": CID})
    assert response.status_code == 401
    (line,) = http_lines(log_lines())
    assert line["service.name"] == "mortgage-knowledge-assistant"
    assert line["correlationId"] == CID
    assert (line["http.method"], line["http.route"], line["http.status"]) == ("POST", main.ASK_PATH, 401)
    assert isinstance(line["durationMs"], (int, float))


def test_unmatched_and_health_paths(log_lines):
    client = TestClient(main.app)
    client.get("/health")
    client.get("/api/v1/assistant/MTG-1001")
    lines = http_lines(log_lines())
    assert [line["http.route"] for line in lines] == ["unmatched"]
    assert "MTG-1001" not in json.dumps(lines)


def test_bearer_tokens_never_reach_the_logs(log_lines):
    TestClient(main.app).post(main.ASK_PATH, json={"question": "x"},
                              headers={"Authorization": "Bearer not.a.real-token-0123456789"})
    text = json.dumps(log_lines())
    assert "not.a.real-token-0123456789" not in text and "Bearer" not in text
