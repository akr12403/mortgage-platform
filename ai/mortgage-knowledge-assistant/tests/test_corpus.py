"""Guards on the real knowledge/v1 corpus (Task 7.1 rules in knowledge/README.md)."""
import re

from src.ingest.chunker import chunk_corpus
from src.ingest.loader import load_corpus
from src.ingest.tokenizer import SimpleTokenizer

REQUIRED_DOCS = {"mortgage-policy-overview", "underwriting-guidelines", "delinquency-playbook", "servicing-faq",
                 "security-policy-excerpt"}


def test_v1_has_the_five_required_documents(corpus_v1):
    docs = load_corpus(corpus_v1)
    assert REQUIRED_DOCS <= {d.doc_id for d in docs}
    assert len(docs) >= 5


def test_v1_chunks_have_unique_ids_and_fit_the_default_size(corpus_v1):
    chunks = chunk_corpus(load_corpus(corpus_v1), SimpleTokenizer(), size=512, overlap=64)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    # Words are a lower bound on tokens; the real tiktoken check is in the README dry run.
    assert all(c.token_count <= 512 for c in chunks)


def test_v1_delinquency_rule_matches_the_platform(corpus_v1):
    playbook = next(d for d in load_corpus(corpus_v1) if d.doc_id == "delinquency-playbook")
    sections = {s.heading: s.text for s in playbook.sections}
    assert {"Definition", "Severity", "Timeline"} <= set(sections)
    assert "30 or more calendar days past due" in sections["Definition"]
    for band, severity in (("30–59", "MODERATE"), ("60–89", "SEVERE"), ("90 or more", "CRITICAL")):
        assert re.search(rf"\|\s*{band}\s*\|\s*`{severity}`", sections["Severity"]), severity


def test_v1_has_loan_type_specific_underwriting_sections(corpus_v1):
    uw = next(d for d in load_corpus(corpus_v1) if d.doc_id == "underwriting-guidelines")
    tagged = {s.heading: s.loan_types for s in uw.sections if len(s.loan_types) == 1}
    assert tagged == {"Conventional loans": ("CONVENTIONAL",), "FHA loans": ("FHA",), "VA loans": ("VA",)}


def test_v1_contains_no_obvious_personal_data_or_secrets(corpus_v1):
    patterns = {
        "email (other than @capstone.local seed accounts)": r"[\w.+-]+@(?!capstone\.local)[\w-]+\.[\w.]+",
        "US SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "phone number": r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b",
        "API key": r"\bsk-[A-Za-z0-9]{16,}",
        "card number": r"\b(?:\d[ -]?){13,16}\b",
    }
    for path in corpus_v1.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for label, pattern in patterns.items():
            assert not re.search(pattern, text), f"{path.name} looks like it contains a {label}"
