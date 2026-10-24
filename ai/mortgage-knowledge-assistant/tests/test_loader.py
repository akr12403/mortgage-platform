import pytest

from src.ingest.loader import INTRO_SECTION, CorpusError, load_corpus, parse_document
from tests.conftest import write_doc


def test_sections_split_at_level_two_headings(tmp_path):
    path = write_doc(tmp_path / "v1", "sample-policy",
                     "# Sample Policy\n\nIntro text.\n\n## Timeline\n\nDay 30.\n\n### Detail\n\nStill timeline.\n\n"
                     "## Escalation\n\nCall the admin.\n")
    doc = parse_document(path, "v1")
    assert [s.heading for s in doc.sections] == [INTRO_SECTION, "Timeline", "Escalation"]
    assert "### Detail" in doc.sections[1].text  # sub-headings stay inside their section
    assert "# Sample Policy" not in doc.sections[0].text  # the title line is dropped
    assert doc.doc_id == "sample-policy" and doc.file_name == "sample-policy.md" and doc.version == "v1"


def test_section_loan_type_tag_overrides_document_types(tmp_path):
    path = write_doc(tmp_path / "v1", "uw", "## General\n\nAll loans.\n\n## FHA loans\n<!-- loanType: FHA -->\n\n"
                     "580 minimum.\n", loan_types="[CONVENTIONAL, FHA, VA]")
    doc = parse_document(path, "v1")
    general, fha = doc.sections
    assert general.loan_types == ("CONVENTIONAL", "FHA", "VA")
    assert fha.loan_types == ("FHA",)
    assert "loanType" not in fha.text


def test_section_tag_outside_document_loan_types_is_rejected(tmp_path):
    path = write_doc(tmp_path / "v1", "uw", "## VA\n<!-- loanType: VA -->\n\ntext\n", loan_types="[FHA]")
    with pytest.raises(CorpusError, match="not in the document's loanTypes"):
        parse_document(path, "v1")


@pytest.mark.parametrize("key, new_line, message", [
    ("docId", "docId: wrong-name", "must be lowercase-kebab-case and equal the file name"),
    ("version", "version: v2", "does not match its folder"),
    ("loanTypes", "loanTypes: [JUMBO]", "unknown loan type"),
    ("loanTypes", "loanTypes: [ALL, FHA]", "cannot combine ALL"),
    ("owner", None, "missing owner"),
])
def test_invalid_front_matter_is_rejected(tmp_path, key, new_line, message):
    path = write_doc(tmp_path / "v1", "doc-a", "## A\n\ntext\n")
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith(key + ":"):
            if new_line is not None:
                lines.append(new_line)
        else:
            lines.append(line)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(CorpusError, match=message):
        parse_document(path, "v1")


def test_missing_front_matter_and_empty_section_are_rejected(tmp_path):
    folder = tmp_path / "v1"
    folder.mkdir()
    (folder / "no-header.md").write_text("# Title\n\n## A\n\ntext\n")
    with pytest.raises(CorpusError, match="missing YAML front matter"):
        parse_document(folder / "no-header.md", "v1")
    path = write_doc(folder, "empty-section", "## A\n\n## B\n\ntext\n")
    with pytest.raises(CorpusError, match="section is empty"):
        parse_document(path, "v1")


def test_load_corpus_ignores_readme_and_sorts_by_name(tmp_path):
    folder = tmp_path / "v1"
    write_doc(folder, "b-doc", "## B\n\ntext\n")
    write_doc(folder, "a-doc", "## A\n\ntext\n")
    (folder / "README.md").write_text("# not part of the corpus\n")
    assert [d.doc_id for d in load_corpus(folder)] == ["a-doc", "b-doc"]


def test_load_corpus_requires_existing_non_empty_folder(tmp_path):
    with pytest.raises(CorpusError, match="not found"):
        load_corpus(tmp_path / "v9")
    (tmp_path / "v1").mkdir()
    with pytest.raises(CorpusError, match="no .md documents"):
        load_corpus(tmp_path / "v1")
