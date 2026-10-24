"""Chat model clients.

`OpenAIChatClient` calls an OpenAI-compatible `POST {LLM_API_BASE}/chat/completions` with structured output
(`response_format: json_schema`, strict), so the reply is always JSON matching the schema in prompts.py.
It does not send `temperature` (reasoning models such as gpt-6-luna reject non-default values); it sends
`max_completion_tokens` and, when configured, `reasoning_effort`.

`ScriptedLLM` returns canned replies for tests and records every request.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from src.http_client import Transport, TransportError, api_error_message, retry_delay, urllib_transport

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The model call failed or returned something unusable. Never contains credentials or prompt text."""


@dataclass(frozen=True)
class LLMReply:
    data: dict
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class ChatModel(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict) -> LLMReply: ...


class OpenAIChatClient:
    RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(self, api_base: str, api_key: str, model: str, *, reasoning_effort: str = "low",
                 max_output_tokens: int = 2000, timeout: float = 60.0, max_retries: int = 3,
                 transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY is not set")
        self._url = api_base.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self.model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport or urllib_transport
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"OpenAIChatClient(model={self.model!r}, url={self._url!r})"

    def complete_json(self, system: str, user: str, schema: dict) -> LLMReply:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": schema},
            "max_completion_tokens": self._max_output_tokens,
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        body = json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        for attempt in range(self._max_retries + 1):
            try:
                status, raw, response_headers = self._transport(self._url, body, headers, self._timeout)
            except TransportError as exc:
                raise LLMError(f"could not reach the LLM API ({exc})") from None
            if status == 200:
                return self._parse(raw)
            if status in self.RETRYABLE and attempt < self._max_retries:
                delay = retry_delay(response_headers, attempt)
                log.warning("LLM API returned %s; retrying in %.1fs (attempt %d/%d)",
                            status, delay, attempt + 1, self._max_retries)
                self._sleep(delay)
                continue
            raise LLMError(f"LLM API returned HTTP {status}: {api_error_message(raw)}")
        raise LLMError("LLM API retries exhausted")  # pragma: no cover

    def _parse(self, raw: bytes) -> LLMReply:
        try:
            response = json.loads(raw)
            choice = response["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("LLM API response was not in the expected format") from None
        if message.get("refusal"):
            raise LLMError("the model refused the request")
        if choice.get("finish_reason") == "length":
            raise LLMError("the model ran out of output tokens (raise LLM_MAX_OUTPUT_TOKENS)")
        try:
            data = json.loads(message.get("content") or "")
        except ValueError:
            raise LLMError("the model reply was not valid JSON") from None
        if not isinstance(data, dict):
            raise LLMError("the model reply was not a JSON object")
        usage = response.get("usage") or {}
        return LLMReply(data, response.get("model", self.model),
                        int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))


class ScriptedLLM:
    """Test double: returns the queued replies in order and records (system, user) for each call."""

    def __init__(self, *replies: dict, model: str = "scripted-llm") -> None:
        self.model = model
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str, schema: dict) -> LLMReply:
        self.calls.append((system, user))
        if not self._replies:
            raise LLMError("ScriptedLLM has no reply queued")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMReply(reply, self.model)


def build_chat_model(settings) -> ChatModel:
    settings.require_llm_credentials()
    return OpenAIChatClient(settings.llm_api_base, settings.llm_api_key, settings.llm_model,
                            reasoning_effort=settings.llm_reasoning_effort,
                            max_output_tokens=settings.llm_max_output_tokens,
                            timeout=settings.llm_timeout_seconds)
