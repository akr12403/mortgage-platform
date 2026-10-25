# AI Governance: Mortgage Knowledge Assistant

How the M7 knowledge assistant is kept accurate, private and under human control (M7 Task 7.5). Applies to every template in [prompt-library.md](./prompt-library.md) and to the service in `ai/mortgage-knowledge-assistant/`.

## Principles

1. **Advisory only.** The assistant explains policy from the approved knowledge base. People make lending and servicing decisions; the assistant never approves, declines, forecloses, waives or changes a status, and no endpoint lets it.
2. **Grounded or silent.** An answer must come from retrieved passages and cite them. If the knowledge base does not cover a question, the assistant says so instead of guessing.
3. **No personal data in, none out.** The corpus is synthetic **Internal** policy text. Borrower data (Confidential and Restricted in `docs/security/security-controls.md`) must never reach a prompt, a log line or an answer.
4. **Traceable.** Every answer can be traced to a user, a corpus version, the chunks cited, a model and a prompt version, through its correlation id.

## Roles and accountability

| Role | Responsibility |
| --- | --- |
| Platform AI team | Service, prompts, threshold calibration, the controls in this document |
| Document owners (header of each knowledge file) | Accuracy of their policy text; approve every corpus change |
| Chief underwriter | Underwriting guidelines and the `underwriting-summary-v1` template; final word on underwriting overrides |
| Servicing operations lead | Delinquency playbook, servicing FAQ, `delinquency-explanation-v1` |
| Security lead | Security policy excerpt, `security-policy-qa-v1`, AI incidents, API key |
| Every user | Acts only on cited answers; never pastes personal data; reports wrong or unsafe answers |

## Human-in-the-loop: when a person must decide

The service sets `requiresHumanApproval: true` when a question is about one of the decision types below **and** concerns a specific case: it names a loan (`MTG-####`), sends `mortgageExternalId`, or asks whether to act ("should we…", "can I…", "this borrower"). A general policy question ("What is forbearance?") is answered without the flag. The flag is set even when the knowledge base cannot answer, because the decision still needs a person. Rules: `src/rag/approval.py`; tests: `tests/test_guards.py`, `tests/test_service.py`, `tests/test_api.py`.

| # | Scenario | Reason code | Who decides | What the assistant does | What is recorded |
| --- | --- | --- | --- | --- | --- |
| 1 | Approve or decline an application ("Should we approve MTG-1002?") | `UNDERWRITING_DECISION` | Underwriter (or admin), with a second reviewer in the guideline's review bands | Explains the criteria and who decides; never recommends an outcome | Decision and written rationale in the loan file, recorded via `POST /api/v1/mortgages/{id}/underwriting-decision` (the token's role is stored on `LoanApproved`) |
| 2 | Exception to a guideline ("Can we accept a 575 score for this borrower?") | `UNDERWRITING_EXCEPTION` | Second underwriter or administrator | Quotes the guideline and the second-review rule | Second reviewer's name and agreement in the loan file |
| 3 | Foreclosure or legal action ("Should we start foreclosure on MTG-1002?") | `FORECLOSURE_OR_LEGAL` | Administrator (default-management review); legal action is outside the platform | Says a person must decide and points to the 90-day escalation (live run: answered, `requiresHumanApproval: true`, cites playbook "Decisions that always need a person") | Servicing event for the escalation |
| 4 | Fee waiver, refund or balance change ("Can I waive the late fee on MTG-1002?") | `FEE_OR_BALANCE_CHANGE` | Administrator | Explains the policy only | Servicing event with approver |
| 5 | Forbearance, modification or repayment plan longer than 6 months | `FORBEARANCE_OR_MODIFICATION` | Underwriter after a documented hardship review | Explains eligibility and the process | Servicing event; plan details in the loan file |
| 6 | Status or severity correction ("Change MTG-1002 back to ACTIVE") | `STATUS_CORRECTION` | Administrator | Explains that cures are not automated and who corrects status | Servicing event "Delinquency cured…" plus the admin's correction |

### When the underwriter must override the assistant

Even when an answer is not flagged, the human's judgement wins. An underwriter or agent **must override** (ignore) assistant output when:

| Situation | Override rule |
| --- | --- |
| The answer conflicts with documents in the loan file (income, appraisal, identity) | The loan file is the evidence; the assistant only knows policy text |
| The answer has no citation, or "insufficient context" | Do not act; read the source policy or ask its owner |
| The cited passage does not say what the answer claims | Treat as a hallucination: do not act, and report it (below) |
| The answer would treat applicants differently on a protected characteristic | Fair-lending rules in the underwriting guidelines apply; report it to the chief underwriter |
| The corpus version cited is older than the current policy | The current approved policy wins; ask for a re-ingest |
| `underwriting-summary-v1` output | Always input to the underwriter's decision; never stored as the decision rationale |

## Logging of prompts and responses

**What is logged** (one INFO line per question, `src/api/main.py`), searchable by correlation id:

```text
[<correlationId>] ask user=<sub> roles=<roles> loanType=<type|-> mortgage=<MTG-id|-> questionChars=<n>
  redacted=<PII types|-> insufficient=<bool> citations=[<chunk ids>] confidence=<0.00> approval=<bool>
  reasons=<codes|-> model=<model> prompt=<prompt version>
```

Plus: the retrieval line (top-k chunk ids and similarities, threshold), a warning when personal data was redacted (types only), dropped invented citations, and provider or store errors (status code and API error text with keys masked).

**What is never logged:** the question text, the prompt sent to the model, the model's answer text, passages, JWTs, API keys, and any personal data. Business ids (`MTG-####`) are Internal and may appear. Tested by `test_audit_log_has_ids_and_decision_but_never_the_question_or_personal_data`.

**Why not log questions and answers?** They are the main channel for accidental personal data. The audit line is enough to reconstruct what happened: the cited chunk ids and the corpus version give the exact source text, and the prompt version gives the exact instructions. If question logging is ever needed for evaluation, it must log the **redacted** question only, under the same retention rules, with security-lead approval.

**Retention:** today, container logs on the local stack only. Planned for AWS (M8/M9): CloudWatch Logs with 30-day retention and KMS encryption, readable by administrators only.

## PII redaction rules

Applied to every question **before** it is embedded, sent to the LLM or logged (`src/rag/redaction.py`). Redaction is a safety net: the rule for users is still "never paste personal data".

| Type | Example pattern | Replaced with |
| --- | --- | --- |
| Email | `name@domain.tld` | `[REDACTED-EMAIL]` |
| US SSN | `123-45-6789` | `[REDACTED-SSN]` |
| Card number | 13–19 digits with optional spaces or dashes | `[REDACTED-CARD]` |
| Phone | `(555) 123-4567`, `+1 555.123.4567` | `[REDACTED-PHONE]` |
| Bank account / routing | "account number 123456789012" | `[REDACTED-ACCOUNT]` |
| Date of birth | "DOB: 04/12/1985" | `[REDACTED-DOB]` |
| API key | `sk-…` | `[REDACTED-API_KEY]` |
| JWT | `eyJ….….…` | `[REDACTED-JWT]` |

**Kept:** business ids (`MTG-1002`, `BOR-001`), ISO dates such as due dates, and policy numbers (43% DTI, 360 months, HTTP status codes). Tests: `test_personal_data_and_credentials_are_redacted`, `test_business_ids_dates_and_policy_numbers_are_kept`, `test_control_5_personal_data_is_redacted_before_retrieval_and_the_llm`.

**Known limit:** names and street addresses cannot be detected reliably with patterns; they are covered by the user rule, by the API returning no borrower data, and by the prompt rule "do not include personal data". A named-entity redactor is a future improvement.

## Hallucination controls tested

The Session 26 mini exercise: each control, the automated test that proves it, and live evidence from the real corpus with `text-embedding-3-small` and `gpt-6-luna` (2026-10-24/25).

| # | Control | Automated tests | Live evidence |
| --- | --- | --- | --- |
| 1 | **Similarity gate per question.** Best retrieved chunk below 0.45 → insufficient context, LLM not called | `test_control_1_below_threshold_returns_insufficient_without_calling_the_llm`, `test_off_corpus_question_returns_insufficient_context_without_calling_the_llm` | "What is the capital of France?" → best 0.073, insufficient, model not called |
| 2 | **Context-only prompt.** The model sees only the top-5 retrieved passages and must answer from them | `test_control_2_llm_sees_only_the_retrieved_top_k_passages`, `test_a_passage_just_under_the_threshold_can_be_cited_once_the_question_passes_the_gate` | Foreclosure question: best 0.494 passed; answer cites the 0.439 "Decisions that always need a person" passage |
| 3 | **Structured output and the model's own "insufficient".** Strict JSON schema; `sufficient: false`, blank or malformed replies become insufficient context | `test_control_3_model_saying_insufficient_wins_even_with_good_retrieval`, `test_malformed_model_output_never_becomes_an_answer` (4 cases), `test_unusable_replies_raise` (5 cases) | First foreclosure run (before the per-question gate): with weak context, the model returned `sufficient: false` rather than guess |
| 4 | **Citation verification in code.** Chunk ids not in this question's context are dropped; none left → insufficient | `test_control_4_invented_citations_are_dropped`, `test_control_4_answer_with_only_invented_citations_becomes_insufficient` | Every live answer's citations were real chunk ids in pgvector (`delinquency-playbook:v1:c-05`, `underwriting-guidelines:v1:c-05`, …) |
| 5 | **PII redaction** before embedding, the LLM and logs | `test_control_5_personal_data_is_redacted_before_retrieval_and_the_llm`, redaction tests above, audit-log test | — |
| 6 | **Prompt-injection guard.** Question cannot open or close prompt tags; passages and question are declared data | `test_prompt_injection_in_question_cannot_close_the_question_tag` | — |
| 7 | **Approval flag** on case decisions, on both paths | `test_case_decisions_require_human_approval` (7 cases), `test_general_policy_questions_do_not` (4), `test_case_decision_is_flagged_even_when_the_knowledge_base_cannot_answer` | Foreclosure question → `requiresHumanApproval: true`, reason `FORECLOSURE_OR_LEGAL` |
| 8 | **Prompt in docs = prompt in code** | `tests/test_prompt_library.py` | — |

**Threshold calibration** (`python -m src.rag.calibrate`, evidence in the service README): hit@5 **11/11** on-corpus questions; on-corpus best similarity 0.528–0.768; off-corpus 0.065–0.374 (strongest: "today's 30-year mortgage rate", a near-domain question the corpus does not answer). The handbook default 0.7 answered only 3 of 11 real questions; **0.45** answers 11/11 and lets 0/6 off-corpus questions reach the model.

**Re-run the exercise** after any change to the corpus, the embedding model, the chat model or a prompt:

```bash
docker build -f docker/Dockerfile.knowledge-assistant --target test -t ka-test .
docker run --rm ka-test
docker compose run --rm knowledge-ingest python -m src.rag.calibrate
docker compose run --rm knowledge-ingest python -m src.rag.ask --debug "What is the capital of France?"
docker compose run --rm knowledge-ingest python -m src.rag.ask --debug "Should we start foreclosure on MTG-1002 at 95 days past due?"
```

## Change management

| Change | Required before release |
| --- | --- |
| Knowledge document | New corpus version folder (`knowledge/v2/`), owner approval in the PR, re-ingest, calibration re-run, README table updated (`knowledge/README.md`) |
| Prompt template | New version id (`ask-v2`), PR reviewed by the template owner, unit tests and calibration questions re-run, this library updated (drift test enforces `ask-*`) |
| Chat model (`LLM_MODEL`) | Add to the OpenAI project's allowed models, re-run the exercise above, record the result in the service README |
| Embedding model | Re-ingest everything (chunks are stored per model), recalibrate the threshold, check the vector size matches migration 005 |
| Threshold or top-k | Calibration evidence recorded in the service README |

## API key and provider

- One **project-scoped, restricted** OpenAI key (Responses, Chat completions and Embeddings only; allowed models `gpt-6-luna` and `text-embedding-3-small`), with an expiry date, a project spend alert and a small prepaid balance with auto-reload off.
- Stored only in the local `.env` (gitignored); in AWS (M8) it moves to Secrets Manager. Never in code, images, logs or tickets. The secret scan blocks commits that contain keys.
- Rotation and leak response: `docs/operations/runbook.md#secrets-rotation`. A leaked key is revoked in the OpenAI dashboard first, then replaced.
- Only Internal, synthetic policy text and redacted questions are sent to the provider.

## Reporting a problem

Report to the security lead (data or secrets) or the platform AI team (wrong answers), quoting the **correlation id** from the response:
- an answer that states something its cited passage does not say;
- an answer that contains personal data;
- a case decision that was not flagged `requiresHumanApproval`;
- an assistant response that tried to follow instructions from inside a document or question.

The team reproduces it from the audit log, adds a failing test, fixes the prompt or rule (new version), and records the fix in the PR.

## Known limitations

- The approval rules are keyword-based: unusual phrasing of a case decision may not be flagged. Users remain bound by the playbook's "Decisions that always need a person".
- Similarity confidence measures retrieval relevance, not the truth of the answer; controls 2–4 cover answer grounding.
- Single-instance, in-memory rate limiting (20 questions per user per minute), as for the other services; shared throttling is an M9 item.
- No answer-quality evaluation set beyond the calibration questions yet; a graded question set is a planned M10 test.
