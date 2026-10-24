# Mortgage Knowledge Assistant

RAG assistant that answers mortgage policy questions from a controlled knowledge base, with citations (Milestone 7). Port `8001`, health `GET /health`.

**Status:** in progress.

| Task | What | Where |
| --- | --- | --- |
| 7.1 | Knowledge base v1 (5 synthetic documents) | [`knowledge/`](knowledge/README.md) |
| 7.2 | Ingestion pipeline: load → chunk → embed → pgvector | `src/ingest/`, `src/embeddings.py`, `src/store/`, `database/migrations/005_knowledge_chunk.sql` |
| 7.3–7.4 | Retrieval, generation and `POST /api/v1/assistant/ask` (JWT-protected) | to come |
| 7.5 | Prompt library and governance | `docs/ai/` (to come) |
| 7.6 | Incident summarization | to come |

## Configuration

All settings come from environment variables (the repo-root `.env`, never committed). See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_API_BASE` | `https://api.openai.com/v1` | OpenAI-compatible API; must be `https://` |
| `LLM_API_KEY` | — (required for real ingests) | Restricted, project-scoped key with a spend limit |
| `LLM_MODEL` | `gpt-6-luna` | Answer generation (Task 7.3) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 1536-dimension embeddings |
| `EMBEDDING_PROVIDER` | `openai` | `fake` = deterministic offline vectors, for tests and dry runs only |
| `KNOWLEDGE_VERSION` | `v1` | Corpus folder under `knowledge/` |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `512` / `64` | Tokens (tiktoken `cl100k_base`) |
| `RAG_TOP_K` / `RAG_SIMILARITY_THRESHOLD` | `5` / `0.7` | Retrieval (Task 7.3) |
| `POSTGRES_*` | as in `.env.example` | Shared capstone database |

**Model deviation from the handbook:** the handbook example `LLM_MODEL=gpt-4o-mini` is deprecated by OpenAI (shutdown 2027-01-14). This service uses `gpt-6-luna`, OpenAI's listed replacement. Embeddings stay on the handbook's `text-embedding-3-small`.

## RAG parameters (recorded)

| Parameter | Value | Notes |
| --- | --- | --- |
| Chunk size | 512 tokens (upper bound) | Chunks follow `##` sections. Every v1 section fits in one chunk (measured: 51 chunks, largest 301 tokens), so each chunk is one whole, citable section. Longer sections are split into overlapping windows. |
| Overlap | 64 tokens | Applies only when a section is split |
| Context line | `<title> - <section>` at the start of every chunk | Counted in the 512; helps both retrieval and the citation |
| Tokenizer | tiktoken `cl100k_base` | The encoding of the text-embedding-3 models |
| Distance | cosine (`vector_cosine_ops`, HNSW index) | Similarity = 1 − cosine distance |
| Top-k / threshold | 5 / 0.7 | Tuned in Task 7.3; tuned values recorded here |

## Ingestion (Task 7.2)

```text
knowledge/v1/*.md ──load──▶ documents + sections ──chunk──▶ chunks (id, section, loan types)
        ──embed (only new/changed)──▶ vectors ──upsert──▶ knowledge_chunk (pgvector) ──▶ delete stale chunks
```

- **Loader** (`src/ingest/loader.py`): reads the YAML header and splits at `##` headings; validates `docId` = file name, `version` = folder, loan types, required fields and non-empty sections.
- **Chunker** (`src/ingest/chunker.py`): stable chunk IDs `<docId>:<version>:c-<NN>`, for example `delinquency-playbook:v1:c-05` (the "Timeline" section).
- **Embedder** (`src/embeddings.py`): batches of 64; retries 429 and 5xx with backoff (honours `Retry-After`); checks the vector size; the key never appears in logs or errors.
- **Store** (`src/store/vector_store.py`): table `knowledge_chunk` from migration 005, with `doc_id`, `doc_file`, `title`, `section`, `loan_types`, `content`, `content_sha256`, `embedding_model`. Static, parameterised SQL.
- **Idempotent and cheap to re-run:** a chunk whose text and model are unchanged is not re-embedded; chunks removed from the corpus are deleted; one transaction per run, so a failure leaves the previous state intact. Each version (`v1`, `v2`) is stored side by side.

### Run it

The ingester runs as a one-off Compose service (it is not started by `docker compose up`). Prerequisites: the `LLM_*` values in `.env`, and Docker running.

```bash
# 1. Start Postgres (now the pgvector image) and apply migrations, including 005
docker compose up -d postgres db-migrate

# 2. Preview the chunks: no API calls, no database writes
docker compose run --rm knowledge-ingest python -m src.ingest --dry-run --show-chunks

# 3. Ingest (embeds ~51 chunks, well under one cent with text-embedding-3-small)
docker compose run --rm knowledge-ingest

# 4. Run it again: expect "embedded 0, unchanged 51"
docker compose run --rm knowledge-ingest

# 5. Inspect the store
docker exec -it capstone-postgres psql -U mortgage_app -d mortgage_intel -c \
  "SELECT chunk_id, section, loan_types, token_count FROM knowledge_chunk ORDER BY chunk_id LIMIT 12;"
```

**Re-run ingestion** after any corpus change, or to load a new version: `KNOWLEDGE_VERSION=v2 docker compose run --rm knowledge-ingest`. The corpus folder is mounted read-only, so edits are picked up without rebuilding the image; code changes need `docker compose build knowledge-ingest`.

Exit codes: `0` success, `2` configuration or corpus error (for example a missing key or a bad front matter), `1` embedding API or database failure.

### Without Docker

```bash
cd ai/mortgage-knowledge-assistant
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
set -a; . ../../.env; set +a          # loads POSTGRES_* and LLM_* (POSTGRES_HOST=localhost)
python -m src.ingest --dry-run --show-chunks
python -m src.ingest
```

## Tests

```bash
cd ai/mortgage-knowledge-assistant && python -m pytest -q tests
# or, matching CI:  docker build -f docker/Dockerfile.knowledge-assistant --target test -t ka-test . && docker run --rm ka-test
```

The tests use a fake embedder and an in-memory store, so they need no API key, network or database. They also check the real `knowledge/v1` corpus: the five required documents, unique chunk IDs, the 30-day rule and severity bands, loan-type sections, and no personal data or keys.

## Troubleshooting

| Message | Fix |
| --- | --- |
| `LLM_API_KEY is not set` | Add it to the repo-root `.env`, or use `--dry-run` |
| `table knowledge_chunk does not exist` | `docker compose up db-migrate` (applies migration 005) |
| db-migrate fails on `CREATE EXTENSION vector` | Postgres is still the plain image: `docker compose up -d --force-recreate postgres` so it uses `pgvector/pgvector:0.8.7-pg17-trixie` |
| `embedding API returned HTTP 401` | Wrong or expired key; create a new one and update `.env` |
| `HTTP 429` / `insufficient_quota` | Out of credits or rate limited; check billing and the project spend limit |
| `HTTP 403` mentioning the model | The project's allowed-models list does not include `EMBEDDING_MODEL` |
