"""Embedding providers.

- `OpenAIEmbedder` calls an OpenAI-compatible `POST {LLM_API_BASE}/embeddings` endpoint (stdlib HTTP, no SDK).
  It batches inputs, retries 429 and 5xx with backoff (honouring Retry-After) and checks the vector size.
  The API key is sent only in the Authorization header; it never appears in logs, exceptions or reprs.
- `FakeEmbedder` is deterministic and offline: a hashed bag-of-words vector. Texts that share words get similar
  vectors, which is enough for unit tests and dry runs. Never use it for a real knowledge base.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from typing import Callable, Protocol, Sequence

from src.http_client import Transport, TransportError, retry_delay, urllib_transport

log = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """The embedding call failed. Messages carry the HTTP status and API error text, never credentials."""


class Embedder(Protocol):
    model: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(self, api_base: str, api_key: str, model: str, dimensions: int = 1536, batch_size: int = 64,
                 max_retries: int = 4, timeout: float = 30.0, transport: Transport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not api_key:
            raise EmbeddingError("LLM_API_KEY is not set")
        self._url = api_base.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._timeout = timeout
        self._transport = transport or urllib_transport
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"OpenAIEmbedder(model={self.model!r}, url={self._url!r})"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(list(texts[start:start + self._batch_size])))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": batch}).encode("utf-8")
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        for attempt in range(self._max_retries + 1):
            try:
                status, payload, response_headers = self._transport(self._url, body, headers, self._timeout)
            except TransportError as exc:
                raise EmbeddingError(f"could not reach the embedding API ({exc})") from None
            if status == 200:
                return self._parse(payload, len(batch))
            if status in self.RETRYABLE and attempt < self._max_retries:
                delay = retry_delay(response_headers, attempt)
                log.warning("Embedding API returned %s; retrying in %.1fs (attempt %d/%d)",
                            status, delay, attempt + 1, self._max_retries)
                self._sleep(delay)
                continue
            raise EmbeddingError(f"embedding API returned HTTP {status}: {self._api_message(payload)}")
        raise EmbeddingError("embedding API retries exhausted")  # pragma: no cover - loop always returns/raises

    @staticmethod
    def _api_message(payload: bytes) -> str:
        try:
            message = json.loads(payload).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            message = ""
        # Defensive: never echo anything that looks like a key back into logs.
        return re.sub(r"sk-[A-Za-z0-9_\-*]{4,}", "sk-***", message)[:300] or "no error message"

    def _parse(self, payload: bytes, expected: int) -> list[list[float]]:
        try:
            data = json.loads(payload)["data"]
            ordered = sorted(data, key=lambda item: item["index"])
            vectors = [[float(x) for x in item["embedding"]] for item in ordered]
        except (ValueError, KeyError, TypeError):
            raise EmbeddingError("embedding API response was not in the expected format") from None
        if len(vectors) != expected:
            raise EmbeddingError(f"embedding API returned {len(vectors)} vectors for {expected} inputs")
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingError(f"model {self.model} returned {len(vector)} dimensions; the vector store "
                                     f"expects {self.dimensions} (EMBEDDING_DIMENSIONS / migration 005)")
        return vectors


class FakeEmbedder:
    """Deterministic offline embedder: L2-normalised hashed bag of lowercase words."""

    _word = re.compile(r"[a-z0-9]+")

    def __init__(self, dimensions: int = 1536, model: str = "fake-hash-embedding") -> None:
        self.model = model
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in self._word.findall(text.lower()):
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector] if norm else vector


def build_embedder(settings) -> Embedder:
    if settings.embedding_provider == "fake":
        return FakeEmbedder(settings.embedding_dimensions)
    settings.require_embedding_credentials()
    return OpenAIEmbedder(settings.llm_api_base, settings.llm_api_key, settings.embedding_model,
                          settings.embedding_dimensions)
