"""Structured logging for the platform's Python services (M9 Task 9.3). Kept identical in
analytics/mortgage-analytics-service/src/observability.py and ai/mortgage-knowledge-assistant/src/observability.py
(tests/contract/test_log_schema.py checks both copies are the same file).

One JSON object per line on stdout, with the same field names the Java services emit (Spring Boot ECS format), so a
single Splunk search works across all four services. Contract: docs/operations/observability.md

    {"@timestamp": "...Z", "log.level": "INFO", "service.name": "...", "log.logger": "...", "message": "...",
     "correlationId": "...", <extra fields>, ["error.type", "error.message", "error.stack_trace"]}

- correlationId comes from a context variable that the HTTP middleware (and the SQS consumer, per event) sets, so
  every line written while handling a request or an event carries it, without passing it to each log call.
- log_http_request() writes the per-request line used for request rate, 5xx rate and latency: method, route
  TEMPLATE (never the raw path: no mortgage numbers, bounded cardinality), status, durationMs. Never headers, query
  strings or bodies, so tokens and personal data stay out of the logs.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

# Attributes every LogRecord has; anything else on a record came from `extra=` and is emitted as a field.
_STANDARD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}
QUIET_PATHS = frozenset({"/health"})  # container health checks every 15 s: not request traffic
_access_logger = logging.getLogger("http.access")
_LEVELS = {"WARNING": "WARN", "CRITICAL": "FATAL"}  # same level names as the Java services (Logback)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        doc: dict = {
            "@timestamp": datetime.fromtimestamp(record.created, timezone.utc)
                                  .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "log.level": _LEVELS.get(record.levelname, record.levelname),
            "service.name": self.service,
            "log.logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = correlation_id_var.get()
        if correlation_id:
            doc["correlationId"] = correlation_id
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_") and key not in doc:
                doc[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            doc["error.type"] = record.exc_info[0].__name__
            doc["error.message"] = str(record.exc_info[1])
            doc["error.stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(doc, default=str, ensure_ascii=False)


def configure_logging(service: str) -> None:
    """Route all logging (including uvicorn's) through one JSON handler on stdout. Idempotent."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers[:] = []
        uvicorn_logger.propagate = True
    # log_http_request() replaces uvicorn's access line (which has no correlation id and is not JSON).
    logging.getLogger("uvicorn.access").disabled = True
    # HTTP client libraries log every outgoing call at INFO with the full URL, query string included: keep them to
    # warnings so URLs with identifiers or keys never reach the logs.
    for name in ("httpx", "httpcore", "urllib3", "botocore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)


def route_template(scope: dict) -> str:
    route = scope.get("route")
    return getattr(route, "path", None) or "unmatched"


def log_http_request(scope: dict, method: str, path: str, status: int, started: float) -> None:
    """One line per request (call in the correlation middleware's finally block, with time.perf_counter() start)."""
    if path in QUIET_PATHS:
        return
    _access_logger.info("http_request", extra={
        "http.method": method,
        "http.route": route_template(scope),
        "http.status": status,
        "durationMs": round((time.perf_counter() - started) * 1000, 1),
    })
