import json
import math

import pytest

from src.embeddings import EmbeddingError, FakeEmbedder, OpenAIEmbedder

KEY = "sk-test-only-not-a-real-key-123456"


class FakeTransport:
    """Scripted HTTP responses; records each request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, body, headers, timeout):
        self.requests.append((url, json.loads(body), headers))
        return self.responses.pop(0)


def ok(vectors):
    data = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    data.reverse()  # the API does not promise order; the client must sort by index
    return 200, json.dumps({"data": data}).encode(), {}


def embedder(transport, **kwargs):
    return OpenAIEmbedder("https://api.example.test/v1", KEY, "text-embedding-3-small", dimensions=3,
                          transport=transport, sleep=lambda s: None, **kwargs)


def test_sends_model_and_bearer_key_and_returns_vectors_in_input_order():
    transport = FakeTransport([ok([[1, 0, 0], [0, 1, 0]])])
    vectors = embedder(transport).embed(["a", "b"])
    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    url, body, headers = transport.requests[0]
    assert url == "https://api.example.test/v1/embeddings"
    assert body == {"model": "text-embedding-3-small", "input": ["a", "b"]}
    assert headers["Authorization"] == f"Bearer {KEY}"


def test_batches_large_inputs():
    transport = FakeTransport([ok([[1, 0, 0]] * 2), ok([[1, 0, 0]] * 2), ok([[1, 0, 0]])])
    assert len(embedder(transport, batch_size=2).embed(["t"] * 5)) == 5
    assert [len(r[1]["input"]) for r in transport.requests] == [2, 2, 1]


def test_retries_rate_limit_and_server_errors_honouring_retry_after():
    slept = []
    transport = FakeTransport([(429, b"{}", {"Retry-After": "2"}), (503, b"{}", {}), ok([[1, 0, 0]])])
    e = OpenAIEmbedder("https://api.example.test/v1", KEY, "m", dimensions=3, transport=transport,
                       sleep=slept.append)
    assert e.embed(["x"]) == [[1.0, 0.0, 0.0]]
    assert slept == [2.0, 2.0]  # Retry-After first, then exponential backoff 2**1


def test_client_errors_fail_without_retry_and_never_leak_the_key():
    body = json.dumps({"error": {"message": f"Incorrect API key provided: {KEY}"}}).encode()
    transport = FakeTransport([(401, body, {})])
    with pytest.raises(EmbeddingError) as info:
        embedder(transport).embed(["x"])
    assert "HTTP 401" in str(info.value) and KEY not in str(info.value) and "sk-***" in str(info.value)
    assert len(transport.requests) == 1


def test_gives_up_after_max_retries():
    transport = FakeTransport([(500, b"{}", {})] * 3)
    with pytest.raises(EmbeddingError, match="HTTP 500"):
        embedder(transport, max_retries=2).embed(["x"])


def test_wrong_dimensions_or_count_is_an_error():
    with pytest.raises(EmbeddingError, match="returned 2 dimensions"):
        embedder(FakeTransport([ok([[1, 0]])])).embed(["x"])
    with pytest.raises(EmbeddingError, match="returned 1 vectors for 2 inputs"):
        embedder(FakeTransport([ok([[1, 0, 0]])])).embed(["x", "y"])


def test_malformed_response_is_an_error():
    with pytest.raises(EmbeddingError, match="expected format"):
        embedder(FakeTransport([(200, b"not json", {})])).embed(["x"])


def test_key_is_required_and_not_in_repr():
    with pytest.raises(EmbeddingError, match="LLM_API_KEY"):
        OpenAIEmbedder("https://api.example.test/v1", "", "m")
    assert KEY not in repr(embedder(FakeTransport([])))


def test_fake_embedder_is_deterministic_normalised_and_similarity_follows_shared_words():
    e = FakeEmbedder(dimensions=256)
    a, a2, b, c = e.embed(["loan is 30 days past due", "loan is 30 days past due",
                           "30 days past due loan contact timeline", "rotate the jwt signing key"])
    cos = lambda x, y: sum(i * j for i, j in zip(x, y))  # noqa: E731 - vectors are unit length
    assert a == a2 and math.isclose(math.sqrt(cos(a, a)), 1.0)
    assert cos(a, b) > cos(a, c)
