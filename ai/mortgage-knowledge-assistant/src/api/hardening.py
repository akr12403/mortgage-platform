"""OWASP API hardening (same baseline as the analytics service, M6 Task 6.3).

- Security headers on every response.
- A small in-memory fixed-window rate limiter (single instance; see docs/security/security-controls.md).
- Correlation IDs: accept a caller's X-Correlation-Id only if it is short and safe to log, else generate one.
"""
from __future__ import annotations

import math
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CONTENT_SECURITY_POLICY = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                                "img-src 'self' data: https://fastapi.tiangolo.com; frame-ancestors 'none'")
PERMISSIONS_POLICY = "geolocation=(), camera=(), microphone=(), payment=(), usb=()"
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": PERMISSIONS_POLICY,
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}

_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def security_headers_for(path: str) -> dict[str, str]:
    headers = dict(SECURITY_HEADERS)
    headers["Content-Security-Policy"] = (DOCS_CONTENT_SECURITY_POLICY if path.startswith(DOCS_PATHS)
                                          else CONTENT_SECURITY_POLICY)
    return headers


def correlation_id_from(header_value: str | None) -> str:
    """Reuse the caller's id when it is safe to put in logs (no spaces, newlines or markup); otherwise new UUID."""
    if header_value and _SAFE_CORRELATION_ID.match(header_value):
        return header_value
    return str(uuid.uuid4())


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after_seconds: int


class RateLimiter:
    """Fixed-window counter per key. Thread-safe; expired windows are swept periodically."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def try_acquire(self, key: str, limit: int, window_seconds: float) -> Decision:
        now = self._clock()
        with self._lock:
            self._calls += 1
            if self._calls % 1000 == 0:
                self._windows = {k: v for k, v in self._windows.items() if v[0] + window_seconds > now}
            start, count = self._windows.get(key, (now, 0))
            if now - start >= window_seconds:
                start, count = now, 0
            if count >= limit:
                return Decision(False, max(1, math.ceil(start + window_seconds - now)))
            self._windows[key] = (start, count + 1)
            return Decision(True, 0)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
