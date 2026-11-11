"""Grounded question answering: redact -> retrieve -> (threshold gate) -> LLM -> verify citations -> answer.

Hallucination controls (each is tested in tests/test_service.py and listed in docs/ai/governance.md):
1. Best retrieved passage below the similarity threshold -> "insufficient context", and the LLM is not called.
2. Otherwise the LLM sees only the top-k retrieved passages and must answer from them (system prompt `ask-v1`).
3. Structured output: the model returns {answer, citedChunkIds, sufficient}; free text cannot pass as an answer.
4. Citations are verified in code: ids the model invents (not in the context) are dropped. If no valid citation
   remains, or the model says the context is insufficient, the response is "insufficient context".
5. Personal data is redacted from the question before it is embedded, sent to the LLM or logged.

Confidence is the question's retrieval score: for an answer, the best similarity found (the value that passed the
gate, so always >= threshold); for insufficient context, a value below the threshold (the best similarity found, capped just under the threshold), matching the API contract
"insufficient context => confidence below threshold".

requiresHumanApproval follows the question (src/rag/approval.py), on both paths: a question that asks to act on a
specific case needs a person whether or not the knowledge base can answer it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.rag import approval
from src.rag.llm import ChatModel, LLMError
from src.rag.prompts import ASK_PROMPT_VERSION, ASK_RESPONSE_SCHEMA, ASK_SYSTEM_PROMPT, build_ask_user_message
from src.rag.redaction import redact
from src.rag.retriever import Retriever

log = logging.getLogger(__name__)

INSUFFICIENT_CONTEXT_ANSWER = ("I can't answer that reliably: the approved knowledge base does not contain "
                               "information on this question. Please check the source policy or ask its owner.")
MAX_QUESTION_CHARS = 1000


@dataclass(frozen=True)
class Citation:
    document_id: str   # file name, e.g. delinquency-playbook.md
    section: str
    chunk_id: str
    similarity: float

    def as_api(self) -> dict:
        return {"documentId": self.document_id, "section": self.section, "chunkId": self.chunk_id}


@dataclass(frozen=True)
class AskResult:
    answer: str
    citations: tuple[Citation, ...]
    confidence: float
    requires_human_approval: bool
    insufficient_context: bool
    approval_reasons: tuple[str, ...] = ()
    redacted_types: tuple[str, ...] = ()
    retrieved: tuple[tuple[str, float], ...] = ()   # (chunk_id, similarity) of the top-k, for logs/debugging
    prompt_version: str = ASK_PROMPT_VERSION
    model: str | None = None                         # None when the LLM was not called
    dropped_citations: tuple[str, ...] = field(default=())

    def as_api(self, correlation_id: str) -> dict:
        return {
            "answer": self.answer,
            "citations": [c.as_api() for c in self.citations],
            "confidence": self.confidence,
            "requiresHumanApproval": self.requires_human_approval,
            "correlationId": correlation_id,
        }


class QuestionError(ValueError):
    """The question is empty or too long (maps to HTTP 400)."""


class AssistantService:
    def __init__(self, retriever: Retriever, llm: ChatModel) -> None:
        self._retriever = retriever
        self._llm = llm

    def ask(self, question: str, loan_type: str | None = None, mortgage_external_id: str | None = None,
            correlation_id: str = "-") -> AskResult:
        question = (question or "").strip()
        if not question:
            raise QuestionError("question must not be empty")
        if len(question) > MAX_QUESTION_CHARS:
            raise QuestionError(f"question must be at most {MAX_QUESTION_CHARS} characters")

        cleaned = redact(question)
        if cleaned.changed:
            log.warning("[%s] personal data removed from question before processing: %s",
                        correlation_id, ",".join(cleaned.redacted_types))
        decision = approval.assess(cleaned.text, mortgage_external_id)

        retrieval = self._retriever.retrieve(cleaned.text, loan_type)
        retrieved = tuple((h.chunk_id, round(h.similarity, 4)) for h in retrieval.hits)
        log.info("[%s] retrieval loanType=%s top=%.3f threshold=%.2f hits=%s", correlation_id, loan_type or "ANY",
                 retrieval.top_similarity, retrieval.threshold, retrieved)

        def insufficient(model: str | None, dropped: tuple[str, ...] = ()) -> AskResult:
            confidence = min(retrieval.top_similarity, max(retrieval.threshold - 0.01, 0.0))
            log.info("[%s] insufficient context (llm_called=%s)", correlation_id, model is not None)
            return AskResult(INSUFFICIENT_CONTEXT_ANSWER, (), round(max(confidence, 0.0), 2), decision.required,
                             True, approval_reasons=decision.reasons, redacted_types=cleaned.redacted_types, retrieved=retrieved, model=model,
                             dropped_citations=dropped)

        if not retrieval.sufficient:
            return insufficient(None)  # control 1: never ask the LLM without grounding

        user_message = build_ask_user_message(cleaned.text, retrieval.relevant, loan_type)
        reply = self._llm.complete_json(ASK_SYSTEM_PROMPT, user_message, ASK_RESPONSE_SCHEMA)
        data = reply.data
        answer = data.get("answer") if isinstance(data.get("answer"), str) else ""
        cited = data.get("citedChunkIds") if isinstance(data.get("citedChunkIds"), list) else []
        sufficient = data.get("sufficient") is True

        by_id = {h.chunk_id: h for h in retrieval.relevant}
        valid = list(dict.fromkeys(cid for cid in cited if isinstance(cid, str) and cid in by_id))
        dropped = tuple(str(cid) for cid in cited if cid not in by_id)
        if dropped:
            log.warning("[%s] model cited ids that were not in the context; dropped: %s", correlation_id, dropped)

        if not sufficient or not valid or not answer.strip():
            return insufficient(reply.model, dropped)

        citations = tuple(Citation(by_id[cid].doc_file, by_id[cid].section, cid, round(by_id[cid].similarity, 4))
                          for cid in valid)
        confidence = round(retrieval.top_similarity, 2)  # >= threshold: the score that passed the gate
        log.info("[%s] answered with %d citation(s), confidence=%.2f, approval=%s, model=%s, tokens=%s/%s",
                 correlation_id, len(citations), confidence, decision.reasons or "no", reply.model,
                 reply.input_tokens, reply.output_tokens)
        return AskResult(answer.strip(), citations, confidence, decision.required, False,
                         approval_reasons=decision.reasons, redacted_types=cleaned.redacted_types,
                         retrieved=retrieved, model=reply.model, dropped_citations=dropped)


__all__ = ["AskResult", "AssistantService", "Citation", "INSUFFICIENT_CONTEXT_ANSWER", "LLMError", "QuestionError"]
