"""Settings for the mortgage knowledge assistant, read from environment variables only (never from code or Git).

Names follow guides/standards.md and the M7 handbook: LLM_API_BASE, LLM_API_KEY, LLM_MODEL, EMBEDDING_MODEL,
plus the shared POSTGRES_* variables. RAG defaults (chunk 512 tokens, overlap 64, top-k 5) are the handbook values;
the similarity threshold is 0.45 instead of 0.7, from the calibration recorded in the service README.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE_DIR = SERVICE_ROOT / "knowledge"

EMBEDDING_PROVIDERS = ("openai", "fake")
REASONING_EFFORTS = ("", "none", "low", "medium", "high")


class ConfigError(RuntimeError):
    """A required setting is missing or invalid. Messages name the variable, never its value."""


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number") from None
    if not 0.0 <= value <= 1.0:
        raise ConfigError(f"{name} must be between 0 and 1")
    return value


@dataclass(frozen=True)
class Settings:
    # LLM / embeddings (OpenAI-compatible API)
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = field(default="", repr=False)  # repr=False: never printed in logs or tracebacks
    llm_model: str = "gpt-6-luna"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_provider: str = "openai"
    llm_reasoning_effort: str = "low"       # sent as reasoning_effort; empty = let the model decide
    llm_max_output_tokens: int = 2000       # includes reasoning tokens
    llm_timeout_seconds: int = 60

    # RAG parameters
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64
    top_k: int = 5
    similarity_threshold: float = 0.45  # calibrated (README "Threshold calibration"); handbook default 0.7

    # Knowledge base
    knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR
    knowledge_version: str = "v1"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "mortgage_intel"
    postgres_user: str = "mortgage_app"
    postgres_password: str = field(default="", repr=False)

    @property
    def corpus_dir(self) -> Path:
        return self.knowledge_dir / self.knowledge_version

    def require_embedding_credentials(self) -> None:
        if self.embedding_provider == "openai" and not self.llm_api_key:
            raise ConfigError("LLM_API_KEY is not set. Add it to your local .env (never commit it), "
                              "or use EMBEDDING_PROVIDER=fake for offline runs.")

    def require_llm_credentials(self) -> None:
        if not self.llm_api_key:
            raise ConfigError("LLM_API_KEY is not set. Add it to your local .env (never commit it).")

    def require_database(self) -> None:
        if not self.postgres_password:
            raise ConfigError("POSTGRES_PASSWORD is not set (see .env.example)")


def load_settings() -> Settings:
    provider = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower() or "openai"
    if provider not in EMBEDDING_PROVIDERS:
        raise ConfigError(f"EMBEDDING_PROVIDER must be one of {', '.join(EMBEDDING_PROVIDERS)}")

    effort = os.getenv("LLM_REASONING_EFFORT", "low").strip().lower()
    if effort not in REASONING_EFFORTS:
        raise ConfigError("LLM_REASONING_EFFORT must be empty or one of none, low, medium, high")

    version = os.getenv("KNOWLEDGE_VERSION", "v1").strip() or "v1"
    if not version.startswith("v") or not version[1:].isdigit():
        raise ConfigError("KNOWLEDGE_VERSION must look like v1, v2, ...")

    settings = Settings(
        llm_api_base=(os.getenv("LLM_API_BASE", "").strip() or "https://api.openai.com/v1").rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip() or "gpt-6-luna",
        embedding_model=os.getenv("EMBEDDING_MODEL", "").strip() or "text-embedding-3-small",
        embedding_dimensions=_int("EMBEDDING_DIMENSIONS", 1536),
        embedding_provider=provider,
        llm_reasoning_effort=effort,
        llm_max_output_tokens=_int("LLM_MAX_OUTPUT_TOKENS", 2000, minimum=100),
        llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 60),
        chunk_size_tokens=_int("RAG_CHUNK_SIZE", 512, minimum=64),
        chunk_overlap_tokens=_int("RAG_CHUNK_OVERLAP", 64, minimum=0),
        top_k=_int("RAG_TOP_K", 5),
        similarity_threshold=_float("RAG_SIMILARITY_THRESHOLD", 0.45),
        knowledge_dir=Path(os.getenv("KNOWLEDGE_DIR", "").strip() or DEFAULT_KNOWLEDGE_DIR),
        knowledge_version=version,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=_int("POSTGRES_PORT", 5432),
        postgres_db=os.getenv("POSTGRES_DB", "mortgage_intel"),
        postgres_user=os.getenv("POSTGRES_USER", "mortgage_app"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    if settings.chunk_overlap_tokens >= settings.chunk_size_tokens:
        raise ConfigError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
    if not settings.llm_api_base.startswith("https://"):
        raise ConfigError("LLM_API_BASE must use https:// (the API key would otherwise travel in clear text)")
    return settings
