"""Load and validate the versioned knowledge corpus (knowledge/vN/*.md).

Each document has a YAML front-matter header (format in knowledge/README.md). The body is split into sections at
level-2 headings (`## `); those headings become the `section` in citations. Text before the first `##` is the
"Introduction" section. A section may narrow its loan types with `<!-- loanType: FHA -->` right under its heading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

LOAN_TYPES = ("CONVENTIONAL", "FHA", "VA")
ALL = "ALL"
REQUIRED_KEYS = ("docId", "title", "version", "loanTypes", "owner", "classification", "lastReviewed")
INTRO_SECTION = "Introduction"

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_LOAN_TYPE_TAG = re.compile(r"\A\s*<!--\s*loanType:\s*([A-Z_,\s]+?)\s*-->\s*\n?")
_DOC_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CorpusError(ValueError):
    """The corpus breaks the knowledge/README.md rules. The message names the file and the problem."""


@dataclass(frozen=True)
class Section:
    heading: str
    text: str
    loan_types: tuple[str, ...]


@dataclass(frozen=True)
class Document:
    doc_id: str
    file_name: str
    title: str
    version: str
    loan_types: tuple[str, ...]
    sections: tuple[Section, ...]


def _loan_types(value: object, where: str) -> tuple[str, ...]:
    items = value if isinstance(value, list) else [value]
    cleaned = tuple(str(item).strip().upper() for item in items if str(item).strip())
    if not cleaned:
        raise CorpusError(f"{where}: loanTypes is empty")
    if ALL in cleaned:
        if len(cleaned) > 1:
            raise CorpusError(f"{where}: loanTypes cannot combine ALL with specific types")
        return (ALL,)
    unknown = [item for item in cleaned if item not in LOAN_TYPES]
    if unknown:
        raise CorpusError(f"{where}: unknown loan type(s) {unknown}; allowed: ALL, {', '.join(LOAN_TYPES)}")
    return tuple(dict.fromkeys(cleaned))


def parse_document(path: Path, expected_version: str) -> Document:
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = _FRONT_MATTER.match(raw)
    if not match:
        raise CorpusError(f"{path.name}: missing YAML front matter (--- ... ---) at the top of the file")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise CorpusError(f"{path.name}: front matter is not valid YAML ({exc.__class__.__name__})") from None
    if not isinstance(meta, dict):
        raise CorpusError(f"{path.name}: front matter must be key: value pairs")

    missing = [key for key in REQUIRED_KEYS if not meta.get(key)]
    if missing:
        raise CorpusError(f"{path.name}: front matter is missing {', '.join(missing)}")

    doc_id = str(meta["docId"]).strip()
    if not _DOC_ID.match(doc_id) or doc_id != path.stem:
        raise CorpusError(f"{path.name}: docId '{doc_id}' must be lowercase-kebab-case and equal the file name")
    version = str(meta["version"]).strip()
    if version != expected_version:
        raise CorpusError(f"{path.name}: version '{version}' does not match its folder '{expected_version}'")
    doc_loan_types = _loan_types(meta["loanTypes"], path.name)

    body = raw[match.end():]
    # Drop the single `# Title` line; it duplicates the front-matter title.
    body = re.sub(r"\A\s*# [^\n]*\n", "", body, count=1)

    sections: list[Section] = []
    parts = re.split(r"^## +(.+?)\s*$", body, flags=re.M)
    intro, rest = parts[0], parts[1:]
    if intro.strip():
        sections.append(Section(INTRO_SECTION, intro.strip(), doc_loan_types))
    for heading, text in zip(rest[0::2], rest[1::2]):
        heading = heading.strip()
        section_types = doc_loan_types
        tag = _LOAN_TYPE_TAG.match(text.lstrip("\n"))
        if tag:
            section_types = _loan_types(tag.group(1).split(","), f"{path.name} § {heading}")
            if doc_loan_types != (ALL,) and not set(section_types) <= set(doc_loan_types):
                raise CorpusError(f"{path.name} § {heading}: section loan types {list(section_types)} "
                                  f"are not in the document's loanTypes {list(doc_loan_types)}")
            text = text.lstrip("\n")[tag.end():]
        if not text.strip():
            raise CorpusError(f"{path.name} § {heading}: section is empty")
        sections.append(Section(heading, text.strip(), section_types))

    if not sections:
        raise CorpusError(f"{path.name}: document has no content")
    return Document(doc_id, path.name, str(meta["title"]).strip(), version, doc_loan_types, tuple(sections))


def load_corpus(corpus_dir: Path) -> list[Document]:
    """All `*.md` files in one version folder, sorted by name. README files are documentation, not corpus."""
    if not corpus_dir.is_dir():
        raise CorpusError(f"corpus folder not found: {corpus_dir}")
    version = corpus_dir.name
    paths = sorted(p for p in corpus_dir.glob("*.md") if p.name.lower() != "readme.md")
    if not paths:
        raise CorpusError(f"{corpus_dir}: no .md documents found")
    documents = [parse_document(path, version) for path in paths]
    seen: set[str] = set()
    for doc in documents:
        if doc.doc_id in seen:
            raise CorpusError(f"duplicate docId '{doc.doc_id}'")
        seen.add(doc.doc_id)
    return documents
