"""Remove personal data from text before it reaches the LLM or a log line.

The knowledge assistant answers policy questions, so it never needs borrower details (security policy: no
Confidential or Restricted data in AI prompts). This is a safety net for users who paste them anyway.
Business IDs (MTG-####, BOR-###, LOAN-###) are Internal and are kept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]\d{4}\b")),
    ("ACCOUNT", re.compile(r"\b(?:account|acct|routing)(?:\s+(?:number|no\.?|#))?[\s:#]*\d{6,17}\b", re.I)),
    ("DOB", re.compile(r"\b(?:dob|date of birth|born(?: on)?)[\s:]*\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b", re.I)),
    ("API_KEY", re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}")),
    ("JWT", re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")),
)


@dataclass(frozen=True)
class Redaction:
    text: str
    redacted_types: tuple[str, ...]  # e.g. ("EMAIL", "PHONE"); empty when nothing was removed

    @property
    def changed(self) -> bool:
        return bool(self.redacted_types)


def redact(text: str) -> Redaction:
    found: list[str] = []
    for label, pattern in _PATTERNS:
        text, count = pattern.subn(f"[REDACTED-{label}]", text)
        if count:
            found.append(label)
    return Redaction(text, tuple(found))
