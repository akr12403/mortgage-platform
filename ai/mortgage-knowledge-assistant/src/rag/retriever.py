"""Retriever: question -> embedding -> top-k chunks from the vector store, gated by the similarity threshold.

The threshold is a question-level gate, matching how it was calibrated (best similarity per question): if the best
chunk reaches it, the question is in scope and all top-k chunks become context; if not, there is no context and
the service answers "insufficient context" without calling the LLM. Filtering chunk by chunk would drop the
passage that answers a question whenever it scores just under the threshold.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.embeddings import Embedder
from src.store.vector_store import RetrievedChunk, VectorStore


@dataclass(frozen=True)
class Retrieval:
    hits: tuple[RetrievedChunk, ...]      # top-k, best first (for logs and calibration)
    relevant: tuple[RetrievedChunk, ...]  # context for the LLM: all hits if the best one passes the gate, else ()
    threshold: float

    @property
    def top_similarity(self) -> float:
        return self.hits[0].similarity if self.hits else 0.0

    @property
    def sufficient(self) -> bool:
        return bool(self.relevant)


class Retriever:
    def __init__(self, embedder: Embedder, store: VectorStore, corpus_version: str, top_k: int = 5,
                 threshold: float = 0.7) -> None:
        self._embedder = embedder
        self._store = store
        self._version = corpus_version
        self.top_k = top_k
        self.threshold = threshold

    def retrieve(self, question: str, loan_type: str | None = None) -> Retrieval:
        [query] = self._embedder.embed([question])
        hits = tuple(self._store.search(query, self._version, self._embedder.model, self.top_k, loan_type))
        relevant = hits if hits and hits[0].similarity >= self.threshold else ()
        return Retrieval(hits, relevant, self.threshold)
