"""Token counting for chunking.

Production uses tiktoken's `cl100k_base`, the encoding of OpenAI's text-embedding-3 models, so "512 tokens" means
the same thing to the chunker and to the embedding API. The Docker image downloads the encoding at build time
(TIKTOKEN_CACHE_DIR) so ingestion never fetches it at runtime.

`SimpleTokenizer` (whitespace-separated words) exists for unit tests and `--tokenizer simple` dry runs only; its
counts differ from tiktoken's, so never use it for a real ingest.
"""
from __future__ import annotations

import re
from typing import Protocol, Sequence

from src.config import ConfigError

ENCODING_NAME = "cl100k_base"


class Tokenizer(Protocol):
    name: str

    def encode(self, text: str) -> list: ...

    def decode(self, tokens: Sequence) -> str: ...


class TiktokenTokenizer:
    name = f"tiktoken:{ENCODING_NAME}"

    def __init__(self) -> None:
        try:
            import tiktoken
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ConfigError("tiktoken is not installed: pip install -r requirements.txt") from exc
        try:
            self._encoding = tiktoken.get_encoding(ENCODING_NAME)
        except Exception as exc:  # first use downloads the encoding file unless TIKTOKEN_CACHE_DIR has it
            raise ConfigError(f"could not load tiktoken encoding {ENCODING_NAME} ({exc.__class__.__name__}); "
                              "connect to the internet once or use the Docker image, which has it cached") from None

    def encode(self, text: str) -> list[int]:
        return self._encoding.encode(text, disallowed_special=())

    def decode(self, tokens: Sequence[int]) -> str:
        return self._encoding.decode(list(tokens))


class SimpleTokenizer:
    """One token per word, keeping its trailing whitespace so decode(encode(text)) == text."""

    name = "simple:words"
    _piece = re.compile(r"\s*\S+\s*|\s+")

    def encode(self, text: str) -> list[str]:
        return self._piece.findall(text)

    def decode(self, tokens: Sequence[str]) -> str:
        return "".join(tokens)


def get_tokenizer(kind: str = "tiktoken") -> Tokenizer:
    if kind == "tiktoken":
        return TiktokenTokenizer()
    if kind == "simple":
        return SimpleTokenizer()
    raise ValueError(f"unknown tokenizer '{kind}' (use tiktoken or simple)")
