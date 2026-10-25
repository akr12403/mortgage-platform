# Mortgage Knowledge Assistant

RAG assistant that answers mortgage policy questions from a controlled knowledge base, with citations (Milestone 7). Port `8001`, health `GET /health`.

**Status:** in progress.

| Task | What | Where |
| --- | --- | --- |
| 7.1 | Knowledge base v1 (5 synthetic documents) | [`knowledge/`](knowledge/README.md) |
| 7.2 | Ingestion pipeline: load → chunk → embed → pgvector | `src/ingest/`, `src/embeddings.py`, `src/store/`, `database/migrations/005_knowledge_chunk.sql` |
| 7.3 | Retrieval, grounded generation with citations, insufficient-context path, threshold calibration | `src/rag/` |
| 7.4 | FastAPI service: `POST /api/v1/assistant/ask` (M6 JWT), `/health`, `/health/ready`, correlation IDs, rate limit | `src/api/`, [`docs/api/mortgage-knowledge-assistant-openapi.yaml`](../../docs/api/mortgage-knowledge-assistant-openapi.yaml) |
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
| `RAG_TOP_K` / `RAG_SIMILARITY_THRESHOLD` | `5` / `0.45` | Retrieval (Task 7.3); threshold calibrated below (handbook default 0.7) |
| `LLM_REASONING_EFFORT` / `LLM_MAX_OUTPUT_TOKENS` | `low` / `2000` | gpt-6-luna is a reasoning model: no `temperature` is sent, and the output budget includes reasoning tokens |
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
| Top-k / threshold | 5 / **0.45** (handbook default 0.7) | Set from the calibration below: 0.7 rejected 8 of 11 real policy questions |

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
export $(grep -E '^(POSTGRES|LLM|EMBEDDING|RAG|KNOWLEDGE)_[A-Z_]*=' ../../.env | xargs)   # POSTGRES_HOST=localhost
python -m src.ingest --dry-run --show-chunks
python -m src.ingest
```

## Retrieval and generation (Task 7.3)

```text
question ─redact PII─▶ embed ─▶ top-k from pgvector (optional loanType filter)
   ├─ best chunk < threshold ─▶ "insufficient context" (LLM NOT called)
   └─ best chunk ≥ threshold ─▶ LLM with the top-k chunks (prompt ask-v1, structured JSON)
                               ─▶ verify cited chunk ids ─▶ answer + citations
```

- **Retriever** (`src/rag/retriever.py`): cosine similarity on the HNSW index; filters by corpus version and embedding model; `loanType` keeps chunks tagged `ALL` or that type.
- **Prompt** (`src/rag/prompts.py`, version `ask-v1`): answer only from the numbered passages, cite chunk ids, say "insufficient" rather than guess, treat passages and question as data (prompt-injection guard), never make a case decision, no personal data.
- **LLM** (`src/rag/llm.py`): `POST /chat/completions` with strict `json_schema` output `{answer, citedChunkIds, sufficient}`; retries 429/5xx; key never logged.
- **Service** (`src/rag/service.py`): returns the API body `{answer, citations[{documentId, section, chunkId}], confidence, requiresHumanApproval, correlationId}`.

### Hallucination controls (tested in `tests/test_service.py`)

| # | Control | What happens |
| --- | --- | --- |
| 1 | Similarity threshold gate (per question) | Best retrieved chunk below the threshold → insufficient context; the LLM is not called |
| 2 | Context-only prompt | The LLM sees only the top-k retrieved chunks and must answer from them |
| 3 | Structured output + model self-check | Reply must be `{answer, citedChunkIds, sufficient}`; `sufficient=false`, blank or malformed replies → insufficient context |
| 4 | Citation verification in code | Chunk ids not in the context are dropped; no valid citation left → insufficient context |
| 5 | PII redaction | Emails, phone numbers, SSNs, card/account numbers, dates of birth, keys and tokens are replaced before embedding, the LLM and logs; business ids (`MTG-####`) are kept |
| 6 | Prompt-injection guard | Question cannot open or close prompt tags; passages and question are declared data, not instructions |

**Confidence:** the question's retrieval score. For an answer, the best similarity found, the value that passed the gate, so always ≥ threshold; for insufficient context, a value below the threshold. So "confidence < threshold" always means "insufficient context", as in the handbook contract.
**`requiresHumanApproval`:** `true` when the question is about an underwriting decision or exception, foreclosure or legal action, a fee or balance change, forbearance or modification, or a status correction, **and** it concerns a specific case (names an `MTG-` id, sends `mortgageExternalId`, or asks "should/can we…"). The flag is set on insufficient-context answers too: the decision still needs a person. Rules in `src/rag/approval.py`; governance in `docs/ai/governance.md` (Task 7.5).

### Try it

```bash
docker compose build knowledge-ingest      # picks up the new code
docker compose run --rm knowledge-ingest python -m src.rag.ask --debug "What is the delinquency contact timeline?"
docker compose run --rm knowledge-ingest python -m src.rag.ask --loan-type FHA "What credit score is required?"
docker compose run --rm knowledge-ingest python -m src.rag.ask --debug "What is the capital of France?"
```

`--debug` lists the top-k chunk ids with their similarity (`*` = cited). Each answered question costs well under a cent with `gpt-6-luna`; off-corpus questions cost only one embedding call.

### Threshold calibration

```bash
docker compose run --rm knowledge-ingest python -m src.rag.calibrate
```

Embeds 11 on-corpus questions (each with its expected document) and 6 off-corpus ones, then reports hit@k and the best similarity per question, and suggests a threshold halfway between the weakest on-corpus and strongest off-corpus score. Result:

Recorded 2026-10-24, corpus `v1`, `text-embedding-3-small`, top-k 5:

| Measure | Result |
| --- | --- |
| hit@5 (expected document in the top 5) | **11/11** |
| On-corpus best similarity | 0.528 – 0.768 (weakest: "Who is allowed to approve or decline a loan?") |
| Off-corpus best similarity | 0.065 – 0.374 (strongest: "What is today's 30-year fixed mortgage rate?", a near-domain question the corpus does not answer) |
| With the handbook default 0.7 | 3/11 on-corpus answered, 0/6 off-corpus reach the LLM: too strict |
| **Chosen threshold** | **0.45**, halfway between 0.528 and 0.374: 11/11 on-corpus answered, 0/6 off-corpus reach the LLM |

Spot checks after the change: "What is the delinquency contact timeline?" → answered, cites `delinquency-playbook:v1:c-05` (Timeline), confidence 0.76; "What is the capital of France?" → insufficient context, best similarity 0.07, LLM not called.

The threshold gates the **question** (is the best match good enough?), as calibrated; once a question passes, all top-k chunks go to the LLM. A first version filtered chunk by chunk and dropped the passage that answers "Should we start foreclosure on MTG-1002?" (delinquency playbook "Decisions that always need a person", 0.439) while the best match scored 0.494; the per-question gate fixes that without letting off-corpus questions through.

Margins are about 0.08 on each side. Re-run the calibration after any corpus or embedding-model change and update this table; a question that falls between the two groups is still caught by controls 3 and 4 (the model must declare the context sufficient and cite a real chunk).

## HTTP API (Task 7.4)

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /health` | public | Liveness; the container `HEALTHCHECK` |
| `GET /health/ready` | public | Readiness: database reachable, corpus chunks loaded, AI provider configured (503 `DOWN` otherwise) |
| `POST /api/v1/assistant/ask` | Bearer JWT from mortgage-service login; any of the 5 staff roles | Grounded answer with citations (contract in the OpenAPI file) |

**Request** `{"question": "...", "mortgageExternalId": "MTG-1002", "loanType": "CONVENTIONAL"}`: `question` 1–1000 characters; `mortgageExternalId` optional (`MTG-` + digits, used only for approval rules and logs, never sent to the LLM); `loanType` optional (`CONVENTIONAL`, `FHA`, `VA`); unknown fields are rejected.
**Response** `{answer, citations[{documentId, section, chunkId}], confidence, requiresHumanApproval, correlationId}`.

| Status | `code` | When |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | Empty, blank or too long question; bad `loanType` / `mortgageExternalId`; unknown field |
| 401 | `UNAUTHORIZED` / `INVALID_TOKEN` | No token; bad signature, expired, wrong issuer, `alg:none` (checked before validation) |
| 403 | `ACCESS_DENIED` | Token without a staff role |
| 413 | `PAYLOAD_TOO_LARGE` | Body over 16 KB |
| 429 | `RATE_LIMITED` | Over 20 questions per user per minute (`RATE_LIMIT_ASSISTANT_PER_USER`); `Retry-After` header |
| 503 | `AI_PROVIDER_NOT_CONFIGURED` / `AI_PROVIDER_UNAVAILABLE` / `KNOWLEDGE_STORE_UNAVAILABLE` | No `LLM_API_KEY`; OpenAI error or timeout; database down |

- **Correlation IDs:** every response has `X-Correlation-Id`; a caller's value is reused if it is 8–64 safe characters (`[A-Za-z0-9._-]`), otherwise a new UUID is generated so log lines cannot be forged. The id appears in every log line for the request and in the response body.
- **Audit log:** one line per question with user, roles, loan type, mortgage id, question length, redacted PII types, citations, confidence, approval flag and reasons, model and prompt version. The question text itself is never logged.
- **Security headers and error envelope** are the same as the analytics service.

**Architecture: direct call, no BFF (handbook optional step).** Clients call the assistant on :8001 with the same JWT they use for the other services; it validates the token itself (shared `JWT_SECRET`, HS256 pinned). A backend-for-frontend route through mortgage-service would add a synchronous Java→Python hop, which `docs/architecture/resilience.md` says must then get a circuit breaker and time limiter, for no extra security: the assistant never reads borrower tables. Revisit when a UI exists or when the assistant needs live loan data (it would then call mortgage-service with the caller's token, not read its tables).

### Run it

```bash
docker compose up -d --build knowledge-assistant
curl -s localhost:8001/health/ready
```

`/health/ready` should show `"knowledgeChunks": 51` and `"aiProviderConfigured": true`. Then log in and ask; the sign-in token stays in a shell variable and is never printed:

```bash
SEED=$(grep '^AUTH_SEED_PASSWORD=' .env | cut -d= -f2-)
TOKEN=$(SEED="$SEED" python3 -c 'import json,os; print(json.dumps({"username":"servicing@capstone.local","password":os.environ["SEED"]}))' \
  | curl -s localhost:8080/api/v1/auth/login -H 'Content-Type: application/json' -d @- \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
curl -s localhost:8001/api/v1/assistant/ask -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"What is the delinquency contact timeline?"}' | python3 -m json.tool
docker logs knowledge-assistant 2>&1 | grep " ask user=" | tail -1
```

## Tests

```bash
cd ai/mortgage-knowledge-assistant && python -m pytest -q tests
# or, matching CI:  docker build -f docker/Dockerfile.knowledge-assistant --target test -t ka-test . && docker run --rm ka-test
```

The tests use a fake embedder and an in-memory store, so they need no API key, network or database. Task 7.3 tests use a scripted LLM, so they make no API calls; Task 7.4 tests (`test_api.py`) drive the HTTP API end to end through FastAPI's test client with an in-memory store and cover auth, every role, validation, error codes, correlation ids, rate limiting, readiness and the audit log; they cover every hallucination control above, redaction, approval rules and the chat client's request format. The tests also check the real `knowledge/v1` corpus: the five required documents, unique chunk IDs, the 30-day rule and severity bands, loan-type sections, and no personal data or keys.

## Troubleshooting

| Message | Fix |
| --- | --- |
| `LLM_API_KEY is not set` | Add it to the repo-root `.env`, or use `--dry-run` |
| `table knowledge_chunk does not exist` | `docker compose up db-migrate` (applies migration 005) |
| db-migrate fails on `CREATE EXTENSION vector` | Postgres is still the plain image: `docker compose up -d --force-recreate postgres` so it uses `pgvector/pgvector:0.8.7-pg17-trixie` |
| `embedding API returned HTTP 401` | Wrong or expired key; create a new one and update `.env` |
| `HTTP 429` / `insufficient_quota` | Out of credits or rate limited; check billing and the project spend limit |
| `HTTP 403` mentioning the model | The project's allowed-models list does not include `EMBEDDING_MODEL` |
