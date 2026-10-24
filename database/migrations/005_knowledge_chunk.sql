-- M7 Task 7.2: vector store for the mortgage knowledge assistant (pgvector).
-- Requires the pgvector-enabled PostgreSQL image (docker-compose.yml: pgvector/pgvector:*-pg17-trixie).
-- Writer: mortgage-knowledge-assistant only (docs/architecture/service-ownership-matrix.md).
-- Contents: chunks of the SYNTHETIC policy corpus in ai/mortgage-knowledge-assistant/knowledge/ (classification:
-- Internal). Never store borrower data here.
-- Idempotent: safe to re-run on existing volumes (applied by the db-migrate compose service).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunk (
    chunk_id        VARCHAR(120) PRIMARY KEY,           -- <docId>:<version>:c-<NN>, returned in citations
    corpus_version  VARCHAR(20)  NOT NULL,               -- knowledge/<version>/
    doc_id          VARCHAR(80)  NOT NULL,
    doc_file        VARCHAR(120) NOT NULL,               -- e.g. delinquency-playbook.md (citation documentId)
    title           VARCHAR(200) NOT NULL,
    section         VARCHAR(200) NOT NULL,               -- the ## heading (citation section)
    loan_types      TEXT[]       NOT NULL,               -- {ALL} or any of {CONVENTIONAL,FHA,VA}
    ordinal         INT          NOT NULL,
    content         TEXT         NOT NULL,               -- exactly the text that was embedded
    token_count     INT          NOT NULL,
    content_sha256  CHAR(64)     NOT NULL,               -- skip re-embedding unchanged chunks
    embedding_model VARCHAR(100) NOT NULL,
    embedding       vector(1536) NOT NULL,               -- text-embedding-3-small
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_knowledge_chunk_loan_types CHECK (
        loan_types <@ ARRAY['ALL','CONVENTIONAL','FHA','VA']::TEXT[] AND cardinality(loan_types) > 0
    )
);

-- Cosine similarity search (the retriever orders by embedding <=> query).
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding_hnsw
    ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_version ON knowledge_chunk (corpus_version);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_loan_types ON knowledge_chunk USING gin (loan_types);
