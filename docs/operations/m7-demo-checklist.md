# M7 Demo & Sign-off Checklist

Automated demo: `bash scripts/m7-demo.sh` (about 10 minutes; `PAUSE=1` waits for Enter before each step, for rehearsal; `BOTH_INCIDENTS=1` adds the well-evidenced incident to step 4). It follows the milestone's demo scenario step by step and makes 2–3 LLM calls per run (well under 5 cents).

## Before the demo

```bash
cd ~/projects/mortgage-platform
docker compose up --build -d && docker compose ps
docker compose run --rm knowledge-ingest
curl -s localhost:8001/health/ready
PAUSE=1 bash scripts/m7-demo.sh
```

`docker compose ps` should show `knowledge-assistant` healthy next to the M5/M6 services. The ingest run should say `embedded 0, unchanged 51` once the corpus is loaded. `/health/ready` should report `"knowledgeChunks": 51` and `"aiProviderConfigured": true`.

Have these open in a browser tab: [prompt-library.md](../ai/prompt-library.md#underwriting-summary-v1) (step 3) and [governance.md](../ai/governance.md) (questions on human approval).

## Demo scenario (maps to the milestone's demo script)

| # | Show (time) | What to say | Pass criteria |
| --- | --- | --- | --- |
| 1 | **Ask "What is the delinquency contact timeline?"** (3 min) | Redact → embed → top-5 from pgvector → gate at 0.45 → `gpt-6-luna` with `ask-v1` (context only, strict JSON) → cited chunk ids verified in code. The citation is a real `knowledge_chunk` row. | 200; day-by-day timeline; citation `delinquency-playbook.md` / Timeline / `delinquency-playbook:v1:c-05`; confidence ≈ 0.76; no-token call → 401 |
| 2 | **Ask an unrelated question** (2 min) | The gate is calibrated: real questions score 0.528–0.768, off-corpus 0.065–0.374. Below the gate the LLM is never called. The near-domain "today's mortgage rate" is rejected too. | answer is the fixed insufficient-context text; `citations: []`; confidence below 0.45 |
| 3 | **Prompt library: underwriting summary** (2 min) | Six versioned templates; `ask-v1` and `incident-summary-v1` are drift-tested against the code. The underwriting template is a checklist with citations: `UNKNOWN` for missing facts, never approve/decline, no protected characteristics. | template, guardrails and worked example on screen; link to the 6 human-decision scenarios |
| 4 | **Incident summarization with the approval flag** (3 min) | ADMIN only (servicing agent → 403). Runbooks come from a fixed catalogue; the code, not the model, decides `requiresHumanApproval`. The vague report is flagged; the DLQ incident (optional) is not. | `INC-2026-0043` → `UNKNOWN`, confidence ≈ 0.3, no runbook, `requiresHumanApproval: true` with reasons; audit line without the incident text |

## Validation (from the milestone)

- [x] **Question answered with ≥ 1 citation from the corpus.** `test_grounded_answer_matches_the_api_contract`, `test_grounded_answer_returns_citations_confidence_and_api_shape`; live over HTTP on 2026-10-25: timeline answer citing `delinquency-playbook:v1:c-05`, confidence 0.76; demo step 1
- [x] **Off-corpus question returns insufficient context.** `test_off_corpus_question_returns_insufficient_context_without_calling_the_llm`, `test_control_1_…`; live: "What is the capital of France?" → best similarity 0.073, LLM not called; calibration 0/6 off-corpus questions reach the LLM; demo step 2
- [x] **Prompt library has ≥ 5 templates.** [prompt-library.md](../ai/prompt-library.md): **6** (`ask-v1`, `underwriting-summary-v1`, `delinquency-explanation-v1`, `security-policy-qa-v1`, `incident-summary-v1`, `insufficient-context-v1`); `test_library_has_at_least_five_templates`
- [x] **Governance doc lists ≥ 3 manual override scenarios.** [governance.md](../ai/governance.md#human-in-the-loop-when-a-person-must-decide): **6** decision scenarios mapped to code reason codes, plus 6 "underwriter must override" situations and 6 incident approval reasons
- [x] **Tests for retriever with mock embedder (optional).** `tests/test_retriever.py` (fake hashed embedder + in-memory store): ranking, per-question gate, off-topic, loan-type filter, version and model isolation

## Definition of Done → evidence

| DoD item | Evidence |
| --- | --- |
| Knowledge base prepared (controlled sources) | `ai/mortgage-knowledge-assistant/knowledge/v1/`: 5 synthetic documents with owners and versions; [knowledge/README.md](../../ai/mortgage-knowledge-assistant/knowledge/README.md) (source of truth, update process, no client data); `test_corpus.py` checks the 30-day rule, severity bands, loan-type sections and no PII or keys |
| Documents chunked and embedded | `python -m src.ingest`: 51 chunks (largest 301 tokens), `text-embedding-3-small`, 1536 dimensions; re-run embeds 0 (`embedded 0, unchanged 51`); migration `005_knowledge_chunk.sql` |
| Vector retrieval working | pgvector `0.8.7-pg17`, HNSW cosine index; calibration hit@5 **11/11**; loan-type filter (FHA question cites only the FHA section) |
| LLM integrated with cite-from-context behaviour | `gpt-6-luna` via Chat Completions with strict `json_schema`; prompt `ask-v1`; citations verified in code (`test_control_4_…`) |
| Citations returned in API response | `POST /api/v1/assistant/ask` → `citations[{documentId, section, chunkId}]` ([OpenAPI](../api/mortgage-knowledge-assistant-openapi.yaml)) |
| Insufficient-context path implemented | per-question gate at the calibrated 0.45, model `sufficient` flag, invented-citation fallback; fixed `insufficient-context-v1` reply |
| Hallucination controls documented and tested | [governance.md](../ai/governance.md#hallucination-controls-tested): 9 controls, each with automated tests and live evidence; threshold calibration recorded in the [service README](../../ai/mortgage-knowledge-assistant/README.md#threshold-calibration) |
| Prompt library created | [prompt-library.md](../ai/prompt-library.md): 6 versioned templates; drift test `tests/test_prompt_library.py` |
| Human approval scenarios documented | [governance.md](../ai/governance.md#human-in-the-loop-when-a-person-must-decide); `requiresHumanApproval` on `/ask` (`src/rag/approval.py`) and `/summarize-incident` (`src/ops/incident.py`) |
| Ops/incident summarization demo available | `POST /api/v1/assistant/summarize-incident`, `python -m src.ops.summarize_incident`; sample incidents `INC-2026-0042` (SEV2, confidence 0.98, `messaging-dlq`) and `INC-2026-0043` (flagged); demo step 4 |
| README documents ingest + ask flow | [service README](../../ai/mortgage-knowledge-assistant/README.md): configuration, RAG parameters, ingestion (re-run command), retrieval and generation, HTTP API, incident summarization, tests, troubleshooting |
| Merged to develop via reviewed PR(s) | PRs **#94–#99** (Tasks 7.1–7.6), each with the three required security checks green; solo project, so review is by the author plus the gates (see M6 limits); peer review below |

## Implementation requirements (from the milestone)

| Requirement | How it is met |
| --- | --- |
| API keys in env only | `LLM_API_KEY` only in the git-ignored `.env`; restricted project key with spend alert and expiry; masked in errors; gitleaks on every PR |
| Rate limit public endpoints | 20 requests per user per minute on `/ask` and `/summarize-incident` (separate counters); 16 KB / 64 KB body limits; health endpoints only are public |
| Citations must map to real chunk ids present in the store | ids come from `knowledge_chunk`; the model's ids are checked against the passages it was given; invented ids are dropped (`test_control_4_…`) |
| No real borrower PII in prompts; synthetic ids in examples | synthetic corpus and incidents; redaction before every LLM call; `mortgageExternalId` never sent to the model; prompts and answers not logged |

## Security review of the new service

The M6 threat model and risk register now cover the assistant: threats **T-26 to T-32** (prompt injection, hallucination, PII to the AI provider, key leak, denial of wallet, over-trusted incident advice, corpus tampering) and risks **R-18 to R-20** (residual 8 Medium, 8 Medium, 3 Low). Security gates on every M7 PR: secrets, SAST and dependency scanning green, including the new FastAPI/uvicorn/PyJWT/tiktoken dependencies.

## Deviations from the handbook (recorded)

| Handbook | Implemented | Why |
| --- | --- | --- |
| `LLM_MODEL=gpt-4o-mini` | `gpt-6-luna` | `gpt-4o-mini` is deprecated by OpenAI (shutdown 2027-01-14); `gpt-6-luna` is the listed replacement |
| Similarity threshold 0.7 | 0.45 (per question) | calibration: 0.7 answered 3 of 11 real questions; 0.45 answers 11/11 and rejects 6/6 off-corpus |
| `knowledge/*.md` (file table) | `knowledge/v1/*.md` | Task 7.1 step 3 asks for a versioned corpus |
| Optional BFF route through mortgage-service | not built; direct call with the same JWT | no security gain, and it would add a synchronous Java→Python hop that needs a circuit breaker (reason in the service README) |

## Sign-off

- [x] **Reviewed by a peer or the instructor** at the M7 review session: demo run, prompt library and governance read, T-26 to T-32 and R-18 to R-20 agreed. Reviewer: **Sumanth Donur**. Review due: **2026-11-10**. Tick this box when the review is done. **Done: reviewed and approved by Sumanth Donur, 2026-11-10.**
