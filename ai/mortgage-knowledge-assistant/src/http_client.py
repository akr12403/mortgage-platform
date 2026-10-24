"""Minimal JSON-over-HTTPS POST used by the embedding and chat clients (stdlib only, so tests can swap it)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable

# transport(url, body, headers, timeout) -> (status, response_body, response_headers)
Transport = Callable[[str, bytes, dict, float], tuple[int, bytes, dict]]


class TransportError(RuntimeError):
    """Network-level failure (DNS, TLS, timeout). The message names the error class only."""


def urllib_transport(url: str, body: bytes, headers: dict, timeout: float) -> tuple[int, bytes, dict]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https enforced in config
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers or {})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransportError(exc.__class__.__name__) from None


def retry_delay(headers: dict, attempt: int) -> float:
    """Seconds to wait before retry `attempt` (0-based): Retry-After if given, else exponential backoff."""
    retry_after = {k.lower(): v for k, v in headers.items()}.get("retry-after")
    try:
        return min(float(retry_after), 60.0) if retry_after else min(2.0 ** attempt, 30.0)
    except ValueError:
        return min(2.0 ** attempt, 30.0)


def api_error_message(payload: bytes) -> str:
    """The API's error text, truncated, with anything that looks like a key masked."""
    try:
        message = json.loads(payload).get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        message = ""
    return re.sub(r"sk-[A-Za-z0-9_\-*]{4,}", "sk-***", message)[:300] or "no error message"
