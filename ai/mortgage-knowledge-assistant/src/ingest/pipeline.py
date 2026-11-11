"""Ingestion pipeline: load -> chunk -> embed (only new or changed chunks) -> upsert -> remove stale chunks.

Re-running is safe and cheap: a chunk whose text and embedding model are unchanged keeps its stored vector, so
re-ingesting an unchanged corpus makes no embedding API calls. Everything for one corpus version is written in a
single transaction, so a failed run leaves the previous state untouched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.embeddings import Embedder
from src.ingest.chunker import Chunk, chunk_corpus
from src.ingest.loader import load_corpus
from src.ingest.tokenizer import Tokenizer
from src.store.vector_store import StoredChunk

log = logging.getLogger(__name__)


@dataclass
class IngestReport:
    corpus_version: str
    documents: int = 0
    chunks: int = 0
    embedded: int = 0
    unchanged: int = 0
    deleted: int = 0
    max_chunk_tokens: int = 0
    dry_run: bool = False
    chunk_ids: list[str] = field(default_factory=list)

    def summary(self) -> str:
        mode = "DRY RUN (nothing embedded or stored)" if self.dry_run else "stored"
        return (f"corpus {self.corpus_version}: {self.documents} documents, {self.chunks} chunks "
                f"(largest {self.max_chunk_tokens} tokens); embedded {self.embedded}, unchanged {self.unchanged}, "
                f"deleted {self.deleted} stale; {mode}")


def ingest(corpus_dir: Path, tokenizer: Tokenizer, embedder: Embedder | None, store, *, chunk_size: int = 512,
           chunk_overlap: int = 64, dry_run: bool = False, batch_size: int = 64) -> tuple[IngestReport, list[Chunk]]:
    documents = load_corpus(corpus_dir)
    chunks = chunk_corpus(documents, tokenizer, chunk_size, chunk_overlap)
    version = corpus_dir.name
    report = IngestReport(version, documents=len(documents), chunks=len(chunks), dry_run=dry_run,
                          max_chunk_tokens=max(c.token_count for c in chunks),
                          chunk_ids=[c.chunk_id for c in chunks])
    if dry_run:
        return report, chunks
    if embedder is None or store is None:
        raise ValueError("embedder and store are required unless dry_run=True")

    store.check_schema(embedder.dimensions)
    stored = store.fingerprints(version)
    todo = [c for c in chunks if stored.get(c.chunk_id) != (c.content_sha256, embedder.model)]
    report.unchanged = len(chunks) - len(todo)
    log.info("Corpus %s: %d chunks, %d need embedding (%s)", version, len(chunks), len(todo), embedder.model)

    try:
        for start in range(0, len(todo), batch_size):
            batch = todo[start:start + batch_size]
            vectors = embedder.embed([c.content for c in batch])
            store.upsert([StoredChunk(c, v, embedder.model) for c, v in zip(batch, vectors)])
            report.embedded += len(batch)
        report.deleted = store.delete_except(version, {c.chunk_id for c in chunks})
        store.commit()
    except Exception:
        store.rollback()
        raise
    return report, chunks
