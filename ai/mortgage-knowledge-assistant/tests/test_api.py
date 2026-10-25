"""HTTP API (Task 7.4): auth, RBAC, validation, error envelope, correlation ids, rate limit, health, and the
ask flow end to end over an in-memory vector store, fake embedder and scripted LLM (no network, no database)."""
import logging
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.config import Settings
from src.embeddings import EmbeddingError, FakeEmbedder
from src.ingest.pipeline import ingest
from src.ingest.tokenizer import SimpleTokenizer
from src.rag.llm import LLMError, ScriptedLLM
from src.store.vector_store import InMemoryVectorStore, VectorStoreError
from tests.conftest import TEST_JWT_SECRET, write_doc

ASK = "/api/v1/assistant/ask"
TIMELINE_ID = "delinquency-playbook:v1:c-01"
EMB = FakeEmbedder(dimensions=512)


def token(roles=("SERVICING_AGENT",), sub="servicing@capstone.local", secret=TEST_JWT_SECRET,
          issuer="capstone-mortgage-auth", expires_in=600):
    now = int(time.time())
    claims = {"sub": sub, "roles": list(roles), "iss": issuer, "iat": now, "exp": now + expires_in}
    return jwt.encode(claims, secret, algorithm="HS256")


def auth(*roles, **kwargs):
    return {"Authorization": f"Bearer {token(roles or ('SERVICING_AGENT',), **kwargs)}"}


class KeepOpenStore(InMemoryVectorStore):
    closes = 0

    def close(self):
        KeepOpenStore.closes += 1


@pytest.fixture
def store(tmp_path):
    folder = tmp_path / "v1"
    write_doc(folder, "delinquency-playbook",
              "## Timeline\n\ndelinquency contact timeline day 30 phone call written notice\n\n"
              "## Cure\n\ncure reinstatement all installments posted\n")
    write_doc(folder, "servicing-faq", "## Rate limits\n\n429 error too many requests retry after header\n")
    s = KeepOpenStore()
    ingest(folder, SimpleTokenizer(), EMB, s)
    return s


def make_client(store, llm, *, embedder=EMB, threshold=0.3, store_factory=None):
    settings = Settings(similarity_threshold=threshold, embedding_model=embedder.model if embedder else "x",
                        llm_api_key="x", postgres_password="x")
    runtime = main.Runtime(settings, embedder, llm, store_factory or (lambda: store))
    main.app.dependency_overrides[main.get_runtime] = lambda: runtime
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_app():
    main.ask_rate_limiter.reset()
    yield
    main.app.dependency_overrides.clear()


def grounded(ids=(TIMELINE_ID,), text="After 30 days the loan is DELINQUENT; call within 2 business days."):
    return {"answer": text, "citedChunkIds": list(ids), "sufficient": True}


# --- health --------------------------------------------------------------------------------------------------

def test_health_is_public_and_has_security_headers_and_correlation_id(store):
    response = make_client(store, ScriptedLLM()).get("/health")
    assert response.status_code == 200 and response.json() == {"status": "UP", "service": "mortgage-knowledge-assistant"}
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert len(response.headers["X-Correlation-Id"]) == 36


def test_ready_reports_store_corpus_and_provider(store):
    body = make_client(store, ScriptedLLM()).get("/health/ready").json()
    assert body["status"] == "UP" and body["corpusVersion"] == "v1"
    assert body["checks"] == {"aiProviderConfigured": True, "database": "UP", "knowledgeChunks": 3}


def test_ready_is_503_when_provider_missing_or_store_down(store):
    response = make_client(store, None).get("/health/ready")
    assert response.status_code == 503 and response.json()["checks"]["aiProviderConfigured"] is False

    class DownStore(InMemoryVectorStore):
        def count(self, version):
            raise VectorStoreError("cannot connect to PostgreSQL at postgres:5432 (secret details)")

    response = make_client(store, ScriptedLLM(), store_factory=DownStore).get("/health/ready")
    assert response.status_code == 503 and response.json()["checks"]["database"] == "DOWN"
    assert "secret details" not in response.text


# --- correlation id ------------------------------------------------------------------------------------------

def test_safe_caller_correlation_id_is_echoed_and_unsafe_one_is_replaced(store):
    client = make_client(store, ScriptedLLM(grounded()))
    response = client.post(ASK, json={"question": "delinquency contact timeline?"},
                           headers={**auth(), "X-Correlation-Id": "demo-run-0001"})
    assert response.headers["X-Correlation-Id"] == "demo-run-0001" == response.json()["correlationId"]
    response = client.get("/health", headers={"X-Correlation-Id": "bad id\nINFO forged log line"})
    assert response.headers["X-Correlation-Id"] != "bad id\nINFO forged log line"
    assert len(response.headers["X-Correlation-Id"]) == 36


# --- auth and RBAC -------------------------------------------------------------------------------------------

def test_missing_token_is_401_in_the_shared_envelope(store):
    response = make_client(store, ScriptedLLM()).post(ASK, json={"question": "timeline?"})
    body = response.json()
    assert response.status_code == 401 and body["code"] == "UNAUTHORIZED"
    assert set(body) == {"code", "message", "correlationId", "timestamp"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("bad", [
    token(secret="attacker-controlled-secret-0123456789-xyz"),
    token(expires_in=-120),
    token(issuer="someone-else"),
    "abc.def.ghi",
])
def test_invalid_tokens_are_401(store, bad):
    response = make_client(store, ScriptedLLM()).post(ASK, json={"question": "timeline?"},
                                                      headers={"Authorization": f"Bearer {bad}"})
    assert response.status_code == 401 and response.json()["code"] == "INVALID_TOKEN"


def test_alg_none_token_is_rejected(store):
    unsigned = jwt.encode({"sub": "x", "roles": ["ADMIN"], "iss": "capstone-mortgage-auth",
                           "exp": int(time.time()) + 600}, key="", algorithm="none")
    response = make_client(store, ScriptedLLM()).post(ASK, json={"question": "timeline?"},
                                                      headers={"Authorization": f"Bearer {unsigned}"})
    assert response.status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "UNDERWRITER", "SERVICING_AGENT", "RISK_ANALYST", "SUPPORT"])
def test_every_staff_role_may_ask(store, role):
    response = make_client(store, ScriptedLLM(grounded())).post(ASK, json={"question": "contact timeline?"},
                                                                 headers=auth(role))
    assert response.status_code == 200


def test_unknown_role_is_403(store):
    response = make_client(store, ScriptedLLM()).post(ASK, json={"question": "timeline?"}, headers=auth("GUEST"))
    assert response.status_code == 403 and response.json()["code"] == "ACCESS_DENIED"


def test_authentication_is_checked_before_validation(store):
    response = make_client(store, ScriptedLLM()).post(ASK, json={"question": ""})
    assert response.status_code == 401


# --- ask -----------------------------------------------------------------------------------------------------

def test_grounded_answer_matches_the_api_contract(store):
    llm = ScriptedLLM(grounded())
    response = make_client(store, llm).post(
        ASK, json={"question": "What is the delinquency contact timeline?", "loanType": "CONVENTIONAL",
                   "mortgageExternalId": "MTG-1002"}, headers=auth())
    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"answer", "citations", "confidence", "requiresHumanApproval", "correlationId"}
    assert body["citations"] == [{"documentId": "delinquency-playbook.md", "section": "Timeline",
                                  "chunkId": TIMELINE_ID}]
    assert body["confidence"] >= 0.3 and body["requiresHumanApproval"] is False
    assert body["correlationId"] == response.headers["X-Correlation-Id"]
    assert "Loan type in scope: CONVENTIONAL" in llm.calls[0][1]


def test_off_corpus_question_returns_insufficient_context_without_calling_the_llm(store):
    llm = ScriptedLLM()
    response = make_client(store, llm).post(ASK, json={"question": "capital of france poem"}, headers=auth())
    body = response.json()
    assert response.status_code == 200 and body["citations"] == [] and body["confidence"] < 0.3
    assert "can't answer that reliably" in body["answer"] and llm.calls == []


def test_case_decision_sets_requires_human_approval(store):
    response = make_client(store, ScriptedLLM(grounded())).post(
        ASK, json={"question": "Can I waive the late fee? delinquency contact timeline", "mortgageExternalId": "MTG-1002"},
        headers=auth())
    assert response.json()["requiresHumanApproval"] is True


@pytest.mark.parametrize("payload, field", [
    ({"question": ""}, "question"),
    ({"question": "x" * 1001}, "question"),
    ({}, "question"),
    ({"question": "timeline?", "loanType": "JUMBO"}, "loanType"),
    ({"question": "timeline?", "mortgageExternalId": "1002"}, "mortgageExternalId"),
    ({"question": "timeline?", "role": "ADMIN"}, "role"),
])
def test_invalid_requests_are_400_validation_error(store, payload, field):
    response = make_client(store, ScriptedLLM()).post(ASK, json=payload, headers=auth())
    body = response.json()
    assert response.status_code == 400 and body["code"] == "VALIDATION_ERROR" and field in body["message"]


def test_whitespace_question_is_400(store):
    response = make_client(store, ScriptedLLM()).post(ASK, json={"question": "   "}, headers=auth())
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION_ERROR"


def test_oversized_body_is_413(store):
    response = make_client(store, ScriptedLLM()).post(ASK, json={"question": "x" * 20000}, headers=auth())
    assert response.status_code == 413 and response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_rate_limit_per_user_returns_429_with_retry_after(store, monkeypatch):
    monkeypatch.setattr(main, "ASK_PER_USER_PER_MINUTE", 2)
    client = make_client(store, ScriptedLLM())
    payload = {"question": "capital of france poem"}  # insufficient context: no LLM reply needed
    assert [client.post(ASK, json=payload, headers=auth()).status_code for _ in range(2)] == [200, 200]
    limited = client.post(ASK, json=payload, headers=auth())
    assert limited.status_code == 429 and limited.json()["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1
    other_user = client.post(ASK, json=payload, headers=auth(sub="risk@capstone.local"))
    assert other_user.status_code == 200


def test_provider_not_configured_is_503(store):
    response = make_client(store, None, embedder=None).post(ASK, json={"question": "timeline?"}, headers=auth())
    assert response.status_code == 503 and response.json()["code"] == "AI_PROVIDER_NOT_CONFIGURED"


def test_provider_failure_is_503_without_details(store):
    llm = ScriptedLLM(LLMError("LLM API returned HTTP 500: upstream detail sk-***"))
    response = make_client(store, llm).post(ASK, json={"question": "delinquency contact timeline?"}, headers=auth())
    assert response.status_code == 503 and response.json()["code"] == "AI_PROVIDER_UNAVAILABLE"
    assert "upstream detail" not in response.text


def test_embedding_failure_is_503(store):
    class BrokenEmbedder(FakeEmbedder):
        def embed(self, texts):
            raise EmbeddingError("embedding API returned HTTP 429: quota")

    response = make_client(store, ScriptedLLM(), embedder=BrokenEmbedder(dimensions=512)).post(
        ASK, json={"question": "timeline?"}, headers=auth())
    assert response.status_code == 503 and response.json()["code"] == "AI_PROVIDER_UNAVAILABLE"


def test_store_failure_is_503(store):
    class DownStore(InMemoryVectorStore):
        def search(self, *args, **kwargs):
            raise VectorStoreError("vector search failed (OperationalError)")

    response = make_client(store, ScriptedLLM(), store_factory=DownStore).post(
        ASK, json={"question": "timeline?"}, headers=auth())
    assert response.status_code == 503 and response.json()["code"] == "KNOWLEDGE_STORE_UNAVAILABLE"


def test_store_connection_is_closed_after_each_request(store):
    before = KeepOpenStore.closes
    make_client(store, ScriptedLLM()).post(ASK, json={"question": "capital of france poem"}, headers=auth())
    assert KeepOpenStore.closes == before + 1


def test_audit_log_has_ids_and_decision_but_never_the_question_or_personal_data(store):
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture(level=logging.INFO)
    root = logging.getLogger("src")
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.INFO)
    try:
        make_client(store, ScriptedLLM(grounded())).post(
            ASK, json={"question": "jane.doe@example.com asks: delinquency contact timeline?"}, headers=auth())
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    log = "\n".join(records)
    assert "ask user=servicing@capstone.local" in log and TIMELINE_ID in log and "redacted=EMAIL" in log
    assert "jane.doe@example.com" not in log and "contact timeline" not in log
