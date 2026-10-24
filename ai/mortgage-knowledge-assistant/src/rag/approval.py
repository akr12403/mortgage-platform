"""Human-in-the-loop rules: when an assistant answer must be reviewed by a person before anyone acts on it.

The assistant explains policy; people make lending and servicing decisions (underwriting guidelines, delinquency
playbook "Decisions that always need a person"). An answer is flagged `requiresHumanApproval` when the question
is about one of those decision types AND points at acting on a case: it names a loan (MTG-####, or the request's
mortgageExternalId) or asks whether to act ("should we...", "can I...", "this borrower").
A general policy question ("What is forbearance?") is answered without the flag.

Rules are deterministic so they can be tested and audited; they are listed in docs/ai/governance.md (Task 7.5).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# (reason code, topic pattern). Matched case-insensitively against the redacted question.
SENSITIVE_TOPICS: tuple[tuple[str, re.Pattern], ...] = (
    ("UNDERWRITING_DECISION", re.compile(r"\b(approv\w*|declin\w*|deny|denial|reject\w*)\b", re.I)),
    ("UNDERWRITING_EXCEPTION", re.compile(r"\b(exception|override|overrid\w+|bend)\b.*\b(guideline\w*|criteria|"
                                          r"dti|ltv|credit score|minimum)\b", re.I)),
    ("FORECLOSURE_OR_LEGAL", re.compile(r"\b(foreclos\w*|legal action|repossess\w*|evict\w*)\b", re.I)),
    ("FEE_OR_BALANCE_CHANGE", re.compile(r"\b(waiv\w*|forgiv\w*|write[- ]?off|refund\w*)\b", re.I)),
    ("FORBEARANCE_OR_MODIFICATION", re.compile(r"\b(forbearance|modification|modify|repayment plan)\b", re.I)),
    ("STATUS_CORRECTION", re.compile(r"\b(change|correct|reset|override|update)\b.*\b(status|severity)\b", re.I)),
)

# Signs that the user wants to act on a specific case rather than understand the policy.
ACTION_INTENT = re.compile(
    r"\bMTG-\d+\b"
    r"|\b(should|shall|can|could|may|do|must)\s+(i|we|you)\b"
    r"|\b(this|that|my|our|the)\s+(borrower|loan|application|applicant|customer|mortgage|case|file)\b"
    r"|\b(go ahead|ok to|okay to|recommend)\b",
    re.I,
)


@dataclass(frozen=True)
class ApprovalDecision:
    required: bool
    reasons: tuple[str, ...]


def assess(question: str, mortgage_external_id: str | None = None) -> ApprovalDecision:
    topics = tuple(code for code, pattern in SENSITIVE_TOPICS if pattern.search(question))
    if not topics:
        return ApprovalDecision(False, ())
    if mortgage_external_id or ACTION_INTENT.search(question):
        return ApprovalDecision(True, topics)
    return ApprovalDecision(False, ())
