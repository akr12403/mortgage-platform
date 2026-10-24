"""Wire settings -> embedder, vector store, retriever, LLM and service (used by the CLIs and, in Task 7.4, the API)."""
from __future__ import annotations

from src.config import Settings
from src.embeddings import build_embedder
from src.rag.llm import build_chat_model
from src.rag.retriever import Retriever
from src.rag.service import AssistantService
from src.store.vector_store import PgVectorStore


def build_retriever(settings: Settings, store: PgVectorStore | None = None) -> Retriever:
    return Retriever(build_embedder(settings), store or PgVectorStore(settings), settings.knowledge_version,
                     top_k=settings.top_k, threshold=settings.similarity_threshold)


def build_service(settings: Settings, store: PgVectorStore | None = None) -> AssistantService:
    return AssistantService(build_retriever(settings, store), build_chat_model(settings))
