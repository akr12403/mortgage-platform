"""Mortgage Knowledge Assistant API (M7 Task 7.4). Port 8001.

    GET  /health                    liveness (container HEALTHCHECK), public
    GET  /health/ready              readiness: database reachable, corpus loaded, AI provider configured; public
    POST /api/v1/assistant/ask      grounded Q&A with citations; JWT (M6) + any staff role; rate limited
    POST /api/v1/assistant/summarize-incident   incident summary + runbook links (Task 7.6); ADMIN; rate limited

Errors use the platform envelope {code, message, correlationId, timestamp} (guides/standards.md).
Every request gets an X-Correlation-Id (the caller's, if safe, else a new UUID) that appears in all log lines.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.hardening import RateLimiter, correlation_id_from, security_headers_for
from src.api.security import (ASSISTANT_ASK, INCIDENT_SUMMARIZE, Principal, api_error, require_roles,
                              validate_settings)
from src.config import ConfigError, Settings, load_settings
from src.embeddings import Embedder, EmbeddingError, build_embedder
from src.rag.llm import ChatModel, LLMError, build_chat_model
from src.ops.incident import MAX_INCIDENT_CHARS, MIN_INCIDENT_CHARS, IncidentInputError, IncidentSummarizer
from src.ops.prompts import INCIDENT_PROMPT_VERSION
from src.rag.prompts import ASK_PROMPT_VERSION
from src.rag.retriever import Retriever
from src.rag.service import AssistantService, QuestionError
from src.observability import configure_logging, correlation_id_var, log_http_request
from src.store.vector_store import PgVectorStore, VectorStoreError

SERVICE_NAME = "mortgage-knowledge-assistant"

# M9 Task 9.3: one JSON object per line with correlationId on every line (docs/operations/observability.md)
configure_logging(SERVICE_NAME)
logger = logging.getLogger(__name__)

ASK_PATH = "/api/v1/assistant/ask"
INCIDENT_PATH = "/api/v1/assistant/summarize-incident"
MAX_BODY_BYTES = {ASK_PATH: 16 * 1024, INCIDENT_PATH: 64 * 1024}
# LLM calls cost money and time: a tighter per-user budget than ordinary writes (60/min).
ASK_PER_USER_PER_MINUTE = int(os.getenv("RATE_LIMIT_ASSISTANT_PER_USER", "20"))
ask_rate_limiter = RateLimiter()


# --- runtime wiring ------------------------------------------------------------------------------------------

@dataclass
class Runtime:
    settings: Settings
    embedder: Embedder | None          # None when LLM_API_KEY is missing: /ask answers 503, /health/ready DOWN
    llm: ChatModel | None
    store_factory: Callable[[], object]  # a new vector-store connection per request (psycopg2 is not thread-safe)


def build_runtime() -> Runtime:
    settings = load_settings()
    settings.require_database()
    embedder = llm = None
    try:
        embedder, llm = build_embedder(settings), build_chat_model(settings)
    except (ConfigError, EmbeddingError, LLMError) as exc:
        logger.warning("AI provider not configured (%s): /ask will return 503 until it is", exc)
    return Runtime(settings, embedder, llm, lambda: PgVectorStore(settings))


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings()  # fail fast if JWT_SECRET is missing/short
    app.state.runtime = build_runtime()  # fail fast on invalid settings or missing POSTGRES_PASSWORD
    yield


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


app = FastAPI(title="Mortgage Knowledge Assistant", version="1.0.0", lifespan=lifespan)


# --- middleware and error envelope ---------------------------------------------------------------------------

def _envelope(request: Request, status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message,
                 "correlationId": getattr(request.state, "correlation_id", "unknown"),
                 "timestamp": datetime.now(timezone.utc).isoformat()},
        headers=headers,
    )


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    declared = request.headers.get("content-length")
    limit = MAX_BODY_BYTES.get(request.url.path)
    if limit and declared and declared.isdigit() and int(declared) > limit:
        response = _envelope(request, 413, "PAYLOAD_TOO_LARGE", f"Request body is limited to {limit // 1024} KB")
    else:
        response = await call_next(request)
    for name, value in security_headers_for(request.url.path).items():
        response.headers.setdefault(name, value)
    return response


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = correlation_id_from(request.headers.get("X-Correlation-Id"))
    request.state.correlation_id = correlation_id
    token = correlation_id_var.set(correlation_id)  # every log line of this request carries it
    started, status = time.perf_counter(), 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Correlation-Id"] = correlation_id
        return response
    finally:
        log_http_request(request.scope, request.method, request.url.path, status, started)
        correlation_id_var.reset(token)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    detail = exc.detail
    if isinstance(detail, dict):
        payload = {**detail, "correlationId": detail.get("correlationId") or correlation_id,
                   "timestamp": detail.get("timestamp", datetime.now(timezone.utc).isoformat())}
    else:
        payload = {"code": "HTTP_ERROR", "message": str(detail), "correlationId": correlation_id,
                   "timestamp": datetime.now(timezone.utc).isoformat()}
    return JSONResponse(status_code=exc.status_code, content=payload, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Same contract as the other services: 400 VALIDATION_ERROR in the shared envelope (not FastAPI's 422 list).
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = ".".join(str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path"))
    message = f"{field}: {first.get('msg', 'invalid value')}" if field else first.get("msg", "Request is invalid")
    return _envelope(request, 400, "VALIDATION_ERROR", message)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Runs outside the correlation middleware (Starlette ServerErrorMiddleware): pass the id explicitly.
    logger.exception("Unhandled request error",
                     extra={"correlationId": getattr(request.state, "correlation_id", "-")})
    return _envelope(request, 500, "INTERNAL_ERROR", "An unexpected error occurred")


# --- health --------------------------------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "UP", "service": SERVICE_NAME}


@app.get("/health/ready")
def ready(runtime: Runtime = Depends(get_runtime)):
    checks: dict[str, object] = {"aiProviderConfigured": runtime.embedder is not None and runtime.llm is not None}
    store = runtime.store_factory()
    try:
        chunks = store.count(runtime.settings.knowledge_version)
        checks["database"] = "UP"
        checks["knowledgeChunks"] = chunks
    except Exception as exc:  # report, never leak details
        logger.warning("Readiness: knowledge store unavailable (%s)", exc.__class__.__name__)
        checks["database"] = "DOWN"
        chunks = 0
    finally:
        store.close()
    is_ready = checks["database"] == "UP" and chunks > 0 and checks["aiProviderConfigured"]
    body = {"status": "UP" if is_ready else "DOWN", "service": SERVICE_NAME,
            "corpusVersion": runtime.settings.knowledge_version, "checks": checks}
    return JSONResponse(status_code=200 if is_ready else 503, content=body)


# --- ask -----------------------------------------------------------------------------------------------------

class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # only these three fields are accepted

    question: str = Field(min_length=1, max_length=1000, description="Policy question; do not include borrower data")
    mortgageExternalId: str | None = Field(default=None, pattern=r"^MTG-\d{4,10}$",
                                           description="Optional business id; used only for approval rules and logs")
    loanType: Literal["CONVENTIONAL", "FHA", "VA"] | None = Field(
        default=None, description="Only use passages tagged ALL or this loan type")


class CitationOut(BaseModel):
    documentId: str
    section: str
    chunkId: str


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    confidence: float
    requiresHumanApproval: bool
    correlationId: str


def enforce_ask_rate_limit(request: Request, principal: Principal = Depends(require_roles(*ASSISTANT_ASK))) -> Principal:
    decision = ask_rate_limiter.try_acquire(f"ask:{principal.subject}", ASK_PER_USER_PER_MINUTE, 60)
    if not decision.allowed:
        raise api_error(request, 429, "RATE_LIMITED", "Too many requests; retry later",
                        {"Retry-After": str(decision.retry_after_seconds)})
    return principal


def get_assistant(request: Request, runtime: Runtime = Depends(get_runtime)):
    if runtime.embedder is None or runtime.llm is None:
        raise api_error(request, 503, "AI_PROVIDER_NOT_CONFIGURED", "The assistant is not configured; try again later")
    store = runtime.store_factory()
    try:
        s = runtime.settings
        retriever = Retriever(runtime.embedder, store, s.knowledge_version, top_k=s.top_k,
                              threshold=s.similarity_threshold)
        yield AssistantService(retriever, runtime.llm)
    finally:
        store.close()


@app.post(ASK_PATH, response_model=AskResponse, tags=["assistant"])
def ask(request: Request, body: AskRequest,
        principal: Principal = Depends(enforce_ask_rate_limit),
        assistant: AssistantService = Depends(get_assistant)):
    correlation_id = request.state.correlation_id
    try:
        result = assistant.ask(body.question, body.loanType, body.mortgageExternalId, correlation_id)
    except QuestionError as exc:
        raise api_error(request, 400, "VALIDATION_ERROR", f"question: {exc}")
    except (EmbeddingError, LLMError) as exc:
        logger.error("[%s] AI provider error: %s", correlation_id, exc)
        raise api_error(request, 503, "AI_PROVIDER_UNAVAILABLE", "The AI provider is unavailable; try again later")
    except VectorStoreError as exc:
        logger.error("[%s] knowledge store error: %s", correlation_id, exc)
        raise api_error(request, 503, "KNOWLEDGE_STORE_UNAVAILABLE", "The knowledge store is unavailable; try again later")

    # Audit line (docs/ai/governance.md): who asked, what was used, what was decided. Never the question text.
    logger.info("[%s] ask user=%s roles=%s loanType=%s mortgage=%s questionChars=%d redacted=%s insufficient=%s "
                "citations=%s confidence=%.2f approval=%s reasons=%s model=%s prompt=%s",
                correlation_id, principal.subject, ",".join(principal.roles), body.loanType or "-",
                body.mortgageExternalId or "-", len(body.question), ",".join(result.redacted_types) or "-",
                result.insufficient_context, [c.chunk_id for c in result.citations], result.confidence,
                result.requires_human_approval, ",".join(result.approval_reasons) or "-",
                result.model or "-", ASK_PROMPT_VERSION)
    return result.as_api(correlation_id)


# --- incident summarization (Task 7.6) -----------------------------------------------------------------------

class IncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incidentText: str = Field(min_length=MIN_INCIDENT_CHARS, max_length=MAX_INCIDENT_CHARS,
                              description="Incident log lines and notes; personal data and secrets are redacted")
    incidentId: str | None = Field(default=None, pattern=r"^INC-\d{4}-\d{4}$")


class TimelineEntry(BaseModel):
    time: str
    event: str


class RunbookLink(BaseModel):
    id: str
    title: str
    link: str


class IncidentResponse(BaseModel):
    incidentId: str | None
    title: str
    severity: Literal["SEV1", "SEV2", "SEV3", "UNKNOWN"]
    summary: str
    impact: str
    timeline: list[TimelineEntry]
    suspectedCause: str
    affectedServices: list[str]
    recommendedActions: list[str]
    runbooks: list[RunbookLink]
    confidence: float
    requiresHumanApproval: bool
    approvalReasons: list[str]
    openQuestions: list[str]
    correlationId: str


def enforce_incident_rate_limit(request: Request,
                                principal: Principal = Depends(require_roles(*INCIDENT_SUMMARIZE))) -> Principal:
    decision = ask_rate_limiter.try_acquire(f"incident:{principal.subject}", ASK_PER_USER_PER_MINUTE, 60)
    if not decision.allowed:
        raise api_error(request, 429, "RATE_LIMITED", "Too many requests; retry later",
                        {"Retry-After": str(decision.retry_after_seconds)})
    return principal


def get_incident_summarizer(request: Request, runtime: Runtime = Depends(get_runtime)) -> IncidentSummarizer:
    if runtime.llm is None:
        raise api_error(request, 503, "AI_PROVIDER_NOT_CONFIGURED", "The assistant is not configured; try again later")
    return IncidentSummarizer(runtime.llm)


@app.post(INCIDENT_PATH, response_model=IncidentResponse, tags=["operations"])
def summarize_incident(request: Request, body: IncidentRequest,
                       principal: Principal = Depends(enforce_incident_rate_limit),
                       summarizer: IncidentSummarizer = Depends(get_incident_summarizer)):
    correlation_id = request.state.correlation_id
    try:
        result = summarizer.summarize(body.incidentText, body.incidentId, correlation_id)
    except IncidentInputError as exc:
        raise api_error(request, 400, "VALIDATION_ERROR", str(exc))
    except LLMError as exc:
        logger.error("[%s] AI provider error: %s", correlation_id, exc)
        raise api_error(request, 503, "AI_PROVIDER_UNAVAILABLE", "The AI provider is unavailable; try again later")

    # Audit line: who, which incident, what was concluded. Never the incident text.
    logger.info("[%s] incident user=%s incidentId=%s textChars=%d redacted=%s severity=%s confidence=%.2f "
                "approval=%s reasons=%s runbooks=%s model=%s prompt=%s",
                correlation_id, principal.subject, body.incidentId or "-", len(body.incidentText),
                ",".join(result.redacted_types) or "-", result.severity, result.confidence,
                result.requires_human_approval, ",".join(result.approval_reasons) or "-",
                [r.id for r in result.runbooks], result.model or "-", INCIDENT_PROMPT_VERSION)
    return result.as_api(correlation_id)
