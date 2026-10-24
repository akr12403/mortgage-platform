import json

import pytest

from src.rag.llm import LLMError, OpenAIChatClient
from src.rag.prompts import ASK_RESPONSE_SCHEMA

KEY = "sk-test-only-not-a-real-key-123456"


class FakeTransport:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, url, body, headers, timeout):
        self.requests.append((url, json.loads(body), headers))
        return self.responses.pop(0)


def chat(content, finish="stop", refusal=None, model="gpt-6-luna-2026-09-01"):
    message = {"role": "assistant", "content": content}
    if refusal:
        message["refusal"] = refusal
    body = {"model": model, "choices": [{"message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 120}}
    return 200, json.dumps(body).encode(), {}


def client(transport, **kwargs):
    return OpenAIChatClient("https://api.example.test/v1", KEY, "gpt-6-luna", transport=transport,
                            sleep=lambda s: None, **kwargs)


GOOD = json.dumps({"answer": "Day 30.", "citedChunkIds": ["a:v1:c-01"], "sufficient": True})


def test_request_uses_structured_output_and_reasoning_model_parameters():
    transport = FakeTransport([chat(GOOD)])
    reply = client(transport, reasoning_effort="low", max_output_tokens=1500).complete_json(
        "system text", "user text", ASK_RESPONSE_SCHEMA)
    url, body, headers = transport.requests[0]
    assert url == "https://api.example.test/v1/chat/completions"
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert body["model"] == "gpt-6-luna"
    assert body["messages"] == [{"role": "system", "content": "system text"}, {"role": "user", "content": "user text"}]
    assert body["response_format"] == {"type": "json_schema", "json_schema": ASK_RESPONSE_SCHEMA}
    assert body["max_completion_tokens"] == 1500 and body["reasoning_effort"] == "low"
    assert "temperature" not in body and "max_tokens" not in body
    assert reply.data["citedChunkIds"] == ["a:v1:c-01"] and reply.model == "gpt-6-luna-2026-09-01"
    assert (reply.input_tokens, reply.output_tokens) == (900, 120)


def test_reasoning_effort_can_be_omitted():
    transport = FakeTransport([chat(GOOD)])
    client(transport, reasoning_effort="").complete_json("s", "u", ASK_RESPONSE_SCHEMA)
    assert "reasoning_effort" not in transport.requests[0][1]


def test_retries_rate_limits_then_succeeds():
    transport = FakeTransport([(429, b"{}", {"Retry-After": "1"}), chat(GOOD)])
    assert client(transport).complete_json("s", "u", ASK_RESPONSE_SCHEMA).data["sufficient"] is True
    assert len(transport.requests) == 2


@pytest.mark.parametrize("response, message", [
    (chat("not json"), "not valid JSON"),
    (chat("[1, 2]"), "not a JSON object"),
    (chat(GOOD, finish="length"), "ran out of output tokens"),
    (chat("", refusal="I can't help with that"), "refused"),
    ((200, b'{"choices": []}', {}), "expected format"),
])
def test_unusable_replies_raise(response, message):
    with pytest.raises(LLMError, match=message):
        client(FakeTransport([response])).complete_json("s", "u", ASK_RESPONSE_SCHEMA)


def test_http_errors_are_reported_without_the_key():
    body = json.dumps({"error": {"message": f"Incorrect API key provided: {KEY}"}}).encode()
    with pytest.raises(LLMError) as info:
        client(FakeTransport([(401, body, {})])).complete_json("s", "u", ASK_RESPONSE_SCHEMA)
    assert "HTTP 401" in str(info.value) and KEY not in str(info.value)
    assert KEY not in repr(client(FakeTransport([])))


def test_missing_key_is_rejected():
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        OpenAIChatClient("https://api.example.test/v1", "", "gpt-6-luna")
