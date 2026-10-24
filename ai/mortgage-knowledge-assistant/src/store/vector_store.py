"""Vector store for knowledge chunks.

`PgVectorStore` uses the `knowledge_chunk` table created by database/migrations/005_knowledge_chunk.sql
(PostgreSQL + pgvector, cosine distance, HNSW index). The assistant service is the only writer of that table
(docs/architecture/service-ownership-matrix.md). All SQL is static and parameterised.

`InMemoryVectorStore` has the same interface for unit tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from src.ingest.chunker import Chunk


class VectorStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredChunk:
    chunk: Chunk
    embedding: list[float]
    embedding_model: str


class VectorStore(Protocol):
    def fingerprints(self, corpus_version: str) -> dict[str, tuple[str, str]]:
        """chunk_id -> (content_sha256, embedding_model) for every stored chunk of one corpus version."""

    def upsert(self, rows: Sequence[StoredChunk]) -> None: ...

    def delete_except(self, corpus_version: str, keep_chunk_ids: set[str]) -> int: ...

    def count(self, corpus_version: str) -> int: ...


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in vector) + "]"


_UPSERT = """
INSERT INTO knowledge_chunk (chunk_id, corpus_version, doc_id, doc_file, title, section, loan_types, ordinal,
                             content, token_count, content_sha256, embedding_model, embedding, ingested_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, NOW())
ON CONFLICT (chunk_id) DO UPDATE SET
    corpus_version = EXCLUDED.corpus_version, doc_id = EXCLUDED.doc_id, doc_file = EXCLUDED.doc_file,
    title = EXCLUDED.title, section = EXCLUDED.section, loan_types = EXCLUDED.loan_types,
    ordinal = EXCLUDED.ordinal, content = EXCLUDED.content, token_count = EXCLUDED.token_count,
    content_sha256 = EXCLUDED.content_sha256, embedding_model = EXCLUDED.embedding_model,
    embedding = EXCLUDED.embedding, ingested_at = NOW()
"""

_FINGERPRINTS = "SELECT chunk_id, content_sha256, embedding_model FROM knowledge_chunk WHERE corpus_version = %s"
_DELETE_EXCEPT = "DELETE FROM knowledge_chunk WHERE corpus_version = %s AND NOT (chunk_id = ANY(%s))"
_COUNT = "SELECT COUNT(*) FROM knowledge_chunk WHERE corpus_version = %s"
_TABLE_EXISTS = "SELECT to_regclass('public.knowledge_chunk') IS NOT NULL"
_EMBEDDING_DIMS = """
SELECT a.atttypmod FROM pg_attribute a
WHERE a.attrelid = 'public.knowledge_chunk'::regclass AND a.attname = 'embedding'
"""


class PgVectorStore:
    def __init__(self, settings, connect=None) -> None:
        self._settings = settings
        self._connect = connect or self._default_connect
        self._conn = None

    def _default_connect(self):
        import psycopg2

        s = self._settings
        s.require_database()
        try:
            return psycopg2.connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db,
                                    user=s.postgres_user, password=s.postgres_password, connect_timeout=5,
                                    application_name="mortgage-knowledge-assistant")
        except psycopg2.OperationalError as exc:
            # The driver message can include host and user but never the password.
            raise VectorStoreError(f"cannot connect to PostgreSQL at {s.postgres_host}:{s.postgres_port} "
                                   f"({str(exc).strip().splitlines()[0][:200]})") from None

    @property
    def conn(self):
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def check_schema(self, dimensions: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute(_TABLE_EXISTS)
            if not cur.fetchone()[0]:
                raise VectorStoreError("table knowledge_chunk does not exist: run the db-migrate service "
                                       "(docker compose up db-migrate) to apply migration 005")
            cur.execute(_EMBEDDING_DIMS)
            stored = cur.fetchone()[0]
        if stored != dimensions:
            raise VectorStoreError(f"knowledge_chunk.embedding is vector({stored}) but the embedding model "
                                   f"produces {dimensions} dimensions")

    def fingerprints(self, corpus_version: str) -> dict[str, tuple[str, str]]:
        with self.conn.cursor() as cur:
            cur.execute(_FINGERPRINTS, (corpus_version,))
            return {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    def upsert(self, rows: Sequence[StoredChunk]) -> None:
        with self.conn.cursor() as cur:
            for row in rows:
                c = row.chunk
                cur.execute(_UPSERT, (c.chunk_id, c.corpus_version, c.doc_id, c.doc_file, c.title, c.section,
                                      list(c.loan_types), c.ordinal, c.content, c.token_count, c.content_sha256,
                                      row.embedding_model, _vector_literal(row.embedding)))

    def delete_except(self, corpus_version: str, keep_chunk_ids: set[str]) -> int:
        with self.conn.cursor() as cur:
            cur.execute(_DELETE_EXCEPT, (corpus_version, sorted(keep_chunk_ids)))
            return cur.rowcount

    def count(self, corpus_version: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(_COUNT, (corpus_version,))
            return int(cur.fetchone()[0])

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.rows: dict[str, StoredChunk] = {}
        self.commits = 0

    def check_schema(self, dimensions: int) -> None:
        return None

    def fingerprints(self, corpus_version: str) -> dict[str, tuple[str, str]]:
        return {cid: (r.chunk.content_sha256, r.embedding_model)
                for cid, r in self.rows.items() if r.chunk.corpus_version == corpus_version}

    def upsert(self, rows: Sequence[StoredChunk]) -> None:
        for row in rows:
            self.rows[row.chunk.chunk_id] = row

    def delete_except(self, corpus_version: str, keep_chunk_ids: set[str]) -> int:
        doomed = [cid for cid, r in self.rows.items()
                  if r.chunk.corpus_version == corpus_version and cid not in keep_chunk_ids]
        for cid in doomed:
            del self.rows[cid]
        return len(doomed)

    def count(self, corpus_version: str) -> int:
        return sum(1 for r in self.rows.values() if r.chunk.corpus_version == corpus_version)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None
