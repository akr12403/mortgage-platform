"""OWASP API hardening for the analytics service (M6 Task 6.3).

- Security headers on every response (the same baseline as the Java services).
- A small in-memory fixed-window rate limiter (single instance; see docs/security/security-controls.md).
- Upload helpers: filename sanitising, content-type allowlist and magic-byte check.
"""
from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable

CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# Swagger UI / ReDoc load scripts and styles, so the interactive docs get a looser (still framing-proof) policy.
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


def security_headers_for(path: str) -> dict[str, str]:
    headers = dict(SECURITY_HEADERS)
    is_docs = path.startswith(DOCS_PATHS)
    headers["Content-Security-Policy"] = DOCS_CONTENT_SECURITY_POLICY if is_docs else CONTENT_SECURITY_POLICY
    return headers


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


# --- uploads -------------------------------------------------------------------------------------------------

ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "text/plain"}
_MAGIC = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
MAX_FILENAME_LENGTH = 100


def sanitize_filename(name: str | None) -> str:
    """Strip any path, keep a conservative character set, never start with a dot, cap the length."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _UNSAFE_FILENAME_CHARS.sub("_", base).strip("._")
    base = re.sub(r"_+", "_", base)
    if len(base) > MAX_FILENAME_LENGTH:
        stem, dot, ext = base.rpartition(".")
        if dot and 0 < len(ext) <= 10:
            base = stem[: MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            base = base[:MAX_FILENAME_LENGTH]
    return base or "document"


def content_matches_type(content_type: str, data: bytes) -> bool:
    """The declared type must be on the allowlist and agree with the file's leading bytes."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        return False
    if content_type == "text/plain":
        if b"\x00" in data:
            return False
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return any(data.startswith(sig) for sig in _MAGIC[content_type])
