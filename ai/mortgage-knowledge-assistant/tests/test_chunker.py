import pytest

from src.ingest.chunker import chunk_document
from src.ingest.loader import parse_document
from src.ingest.tokenizer import SimpleTokenizer
from tests.conftest import write_doc

TOK = SimpleTokenizer()


def _doc(tmp_path, body, **kwargs):
    return parse_document(write_doc(tmp_path / "v1", "playbook", body, title="Playbook", **kwargs), "v1")


def test_short_sections_become_one_chunk_each_with_context_line(tmp_path):
    doc = _doc(tmp_path, "## Timeline\n\nDay 30 marks the loan delinquent.\n\n## Cure\n\nAll installments posted.\n")
    chunks = chunk_document(doc, TOK, size=512, overlap=64)
    assert [c.chunk_id for c in chunks] == ["playbook:v1:c-01", "playbook:v1:c-02"]
    assert [c.section for c in chunks] == ["Timeline", "Cure"]
    assert chunks[0].content.startswith("Playbook - Timeline\n\n")
    assert "Day 30 marks the loan delinquent." in chunks[0].content
    assert chunks[0].doc_file == "playbook.md" and chunks[0].corpus_version == "v1"


def test_long_section_is_split_with_overlap_and_never_exceeds_size(tmp_path):
    words = " ".join(f"w{i}" for i in range(300))
    doc = _doc(tmp_path, f"## Long\n\n{words}\n")
    chunks = chunk_document(doc, TOK, size=100, overlap=20)
    assert len(chunks) > 1
    assert all(c.token_count <= 100 for c in chunks)
    assert all(c.section == "Long" for c in chunks)
    first = chunks[0].content.split()
    second = chunks[1].content.split()
    # Window 2 starts 20 words before window 1 ends (after the 3-word "Playbook - Long" context line).
    assert first[-20:] == second[3:23]
    # Every word of the section appears in some chunk.
    seen = {w for c in chunks for w in c.content.split()}
    assert {f"w{i}" for i in range(300)} <= seen


def test_chunks_never_cross_sections(tmp_path):
    doc = _doc(tmp_path, "## A\n\nalpha beta\n\n## B\n\ngamma delta\n")
    a, b = chunk_document(doc, TOK, size=50, overlap=5)
    assert "gamma" not in a.content and "alpha" not in b.content


def test_chunk_ids_and_hashes_are_deterministic(tmp_path):
    doc = _doc(tmp_path, "## A\n\nsame text\n")
    first, second = chunk_document(doc, TOK), chunk_document(doc, TOK)
    assert [(c.chunk_id, c.content_sha256) for c in first] == [(c.chunk_id, c.content_sha256) for c in second]


def test_loan_types_flow_from_section_to_chunk(tmp_path):
    doc = _doc(tmp_path, "## General\n\nall\n\n## FHA\n<!-- loanType: FHA -->\n\n580\n",
               loan_types="[CONVENTIONAL, FHA, VA]")
    general, fha = chunk_document(doc, TOK)
    assert general.loan_types == ("CONVENTIONAL", "FHA", "VA") and fha.loan_types == ("FHA",)


@pytest.mark.parametrize("size, overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_size_or_overlap_is_rejected(tmp_path, size, overlap):
    doc = _doc(tmp_path, "## A\n\ntext\n")
    with pytest.raises(ValueError):
        chunk_document(doc, TOK, size=size, overlap=overlap)
