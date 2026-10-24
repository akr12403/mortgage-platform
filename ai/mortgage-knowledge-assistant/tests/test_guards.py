"""Redaction, human-approval rules and threshold calibration helpers."""
import pytest

from src.rag.approval import assess
from src.rag.calibrate import suggest_threshold
from src.rag.redaction import redact


@pytest.mark.parametrize("text, label, secret", [
    ("email jane.doe@example.com please", "EMAIL", "jane.doe@example.com"),
    ("call (555) 123-4567 today", "PHONE", "(555) 123-4567"),
    ("call +1 555.123.4567 today", "PHONE", "555.123.4567"),
    ("ssn 123-45-6789", "SSN", "123-45-6789"),
    ("card 4111 1111 1111 1111", "CARD", "4111 1111 1111 1111"),
    ("account number 123456789012", "ACCOUNT", "123456789012"),
    ("DOB: 04/12/1985", "DOB", "04/12/1985"),
    ("key sk-abcdefghijklmnop1234", "API_KEY", "sk-abcdefghijklmnop1234"),
    ("token eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl", "JWT", "eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl"),
])
def test_personal_data_and_credentials_are_redacted(text, label, secret):
    result = redact(text)
    assert secret not in result.text and f"[REDACTED-{label}]" in result.text and label in result.redacted_types


@pytest.mark.parametrize("text", [
    "What happens to MTG-1002 at 30 days past due?",
    "BOR-001 asked about the 2026-03-15 due date and a 43% DTI on a 360-month term",
    "Why do I get a 429 error after 60 requests per minute?",
])
def test_business_ids_dates_and_policy_numbers_are_kept(text):
    result = redact(text)
    assert result.text == text and not result.changed


@pytest.mark.parametrize("question, reason", [
    ("Should we approve MTG-1002?", "UNDERWRITING_DECISION"),
    ("Can I decline this application because the DTI is 52%?", "UNDERWRITING_DECISION"),
    ("Can we make an exception to the minimum credit score for this borrower?", "UNDERWRITING_EXCEPTION"),
    ("Is it OK to start foreclosure on MTG-1002?", "FORECLOSURE_OR_LEGAL"),
    ("Can I waive the late fee for this borrower?", "FEE_OR_BALANCE_CHANGE"),
    ("Should I offer forbearance to the borrower on MTG-1003?", "FORBEARANCE_OR_MODIFICATION"),
    ("Can I change the status of MTG-1002 back to ACTIVE?", "STATUS_CORRECTION"),
])
def test_case_decisions_require_human_approval(question, reason):
    decision = assess(question)
    assert decision.required and reason in decision.reasons


@pytest.mark.parametrize("question", [
    "Who is allowed to approve or decline a loan?",
    "What is forbearance?",
    "What is the delinquency contact timeline?",
    "Why do I get a 403 error?",
])
def test_general_policy_questions_do_not(question):
    assert not assess(question).required


def test_a_mortgage_id_on_the_request_makes_a_decision_topic_case_specific():
    assert assess("What about forbearance?", mortgage_external_id="MTG-1002").required
    assert not assess("What is the timeline?", mortgage_external_id="MTG-1002").required


def test_threshold_suggestion_is_midpoint_when_scores_separate():
    threshold, message = suggest_threshold([0.62, 0.55, 0.71], [0.21, 0.33])
    assert threshold == 0.44 and "suggested RAG_SIMILARITY_THRESHOLD=0.44" in message


def test_threshold_suggestion_reports_overlap():
    threshold, message = suggest_threshold([0.40, 0.70], [0.45])
    assert threshold is None and "overlap" in message
