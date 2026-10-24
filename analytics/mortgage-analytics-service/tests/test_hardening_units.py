"""Task 6.3: pure-unit checks for the analytics hardening helpers (no FastAPI needed)."""
from src.api.hardening import (CONTENT_SECURITY_POLICY, DOCS_CONTENT_SECURITY_POLICY, RateLimiter,
                               content_matches_type, sanitize_filename, security_headers_for)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_rate_limiter_blocks_after_limit_and_resets_with_window():
    clock = FakeClock()
    limiter = RateLimiter(clock)
    assert limiter.try_acquire("u", 2, 60).allowed
    assert limiter.try_acquire("u", 2, 60).allowed
    blocked = limiter.try_acquire("u", 2, 60)
    assert not blocked.allowed and 1 <= blocked.retry_after_seconds <= 60
    assert limiter.try_acquire("other", 2, 60).allowed
    clock.now += 61
    assert limiter.try_acquire("u", 2, 60).allowed


def test_sanitize_filename_strips_paths_and_odd_characters():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\win.ini") == "win.ini"
    assert sanitize_filename("my deed (final).pdf") == "my_deed_final_.pdf"
    assert sanitize_filename(".hidden") == "hidden"
    assert sanitize_filename("") == "document"
    assert sanitize_filename(None) == "document"
    assert sanitize_filename("<script>alert(1)</script>.txt") == "script_.txt"   # "/" splits the path
    long = sanitize_filename("a" * 300 + ".pdf")
    assert len(long) == 100 and long.endswith(".pdf")


def test_content_type_allowlist_and_magic_bytes():
    assert content_matches_type("application/pdf", b"%PDF-1.7\n...")
    assert content_matches_type("image/png", b"\x89PNG\r\n\x1a\n....")
    assert content_matches_type("image/jpeg", b"\xff\xd8\xff\xe0....")
    assert content_matches_type("text/plain", "plain note ✓".encode())
    assert not content_matches_type("application/pdf", b"MZ\x90\x00 an exe pretending")
    assert not content_matches_type("text/plain", b"\x00\x01binary")
    assert not content_matches_type("application/x-msdownload", b"MZ")
    assert not content_matches_type("text/html", b"<html>")


def test_security_headers_strict_csp_except_docs():
    api = security_headers_for("/api/v1/analytics/portfolio-summary")
    assert api["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert api["X-Content-Type-Options"] == "nosniff" and api["X-Frame-Options"] == "DENY"
    assert security_headers_for("/docs")["Content-Security-Policy"] == DOCS_CONTENT_SECURITY_POLICY
