"""Section-aware chunking: documents -> chunks of at most `size` tokens with `overlap` tokens between neighbours.

Rules (recorded in the service README):
- A chunk never crosses a section boundary, so every chunk has exactly one citable `section`.
- Every chunk starts with a context line "<document title> - <section>" so the embedding and the LLM see where
  the passage comes from. The line counts toward the size limit.
- A section that fits in one chunk stays whole. A longer section is split into overlapping windows.
- Chunk IDs are stable and readable: `<docId>:<version>:c-<NN>` (NN = position in the document, from 01).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.ingest.loader import Document
from src.ingest.tokenizer import Tokenizer


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_file: str
    title: str
    section: str
    loan_types: tuple[str, ...]
    corpus_version: str
    ordinal: int
    content: str
    token_count: int

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def chunk_id(doc_id: str, version: str, ordinal: int) -> str:
    return f"{doc_id}:{version}:c-{ordinal:02d}"


def chunk_document(doc: Document, tokenizer: Tokenizer, size: int = 512, overlap: int = 64) -> list[Chunk]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be positive and overlap smaller than size")
    chunks: list[Chunk] = []
    for section in doc.sections:
        prefix = f"{doc.title} - {section.heading}\n\n"
        budget = size - len(tokenizer.encode(prefix))
        if budget <= overlap:
            raise ValueError(f"{doc.file_name} § {section.heading}: heading is too long for chunk size {size}")
        body = tokenizer.encode(section.text)
        step = budget - overlap
        start = 0
        while True:
            end = min(start + budget, len(body))
            content = prefix + tokenizer.decode(body[start:end]).strip()
            # Re-encoding joined text can merge tokens differently at the boundary; trim until it fits.
            while len(tokenizer.encode(content)) > size and end > start + 1:
                end -= 1
                content = prefix + tokenizer.decode(body[start:end]).strip()
            ordinal = len(chunks) + 1
            chunks.append(Chunk(
                chunk_id=chunk_id(doc.doc_id, doc.version, ordinal),
                doc_id=doc.doc_id,
                doc_file=doc.file_name,
                title=doc.title,
                section=section.heading,
                loan_types=section.loan_types,
                corpus_version=doc.version,
                ordinal=ordinal,
                content=content,
                token_count=len(tokenizer.encode(content)),
            ))
            if end >= len(body):
                break
            start = max(start + 1, min(start + step, end - overlap))
    return chunks


def chunk_corpus(documents: list[Document], tokenizer: Tokenizer, size: int = 512, overlap: int = 64) -> list[Chunk]:
    return [chunk for doc in documents for chunk in chunk_document(doc, tokenizer, size, overlap)]
