"""OpenAI-compatible chat-completions stub for the pipeline's E2E run (M10 journey J5). Not used anywhere else.

The knowledge assistant runs its real code path: redaction, retrieval (offline embedder), the similarity gate, the
LLM call, citation verification and the response contract. Only the model is replaced. The stub answers with the
first passage the assistant sent and cites that passage's chunk id, so a passing J5 proves that a citation the API
returns really came from a retrieved passage. With no passages it says the context is insufficient.

Started by tests/e2e/docker-compose.e2e.yml (scripts/ci/e2e-tests.sh) over HTTPS, because the assistant refuses a
non-https LLM_API_BASE. Locally, J5 runs against your real LLM instead (tests/e2e/README.md).
"""
from __future__ import annotations

import json
import os
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASSAGE = re.compile(r'<passage chunkId="([^"]+)"[^>]*>\n(.*?)\n</passage>', re.S)
MARKDOWN = re.compile(r"[#*`>_|]+")


def first_sentence(text: str, limit: int = 300) -> str:
    plain = " ".join(MARKDOWN.sub(" ", text).split())
    sentence = re.split(r"(?<=[.!?])\s", plain, maxsplit=1)[0]
    return sentence[:limit].strip()


def reply_for(messages: list[dict]) -> dict:
    user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    passages = PASSAGE.findall(user)
    if not passages:
        return {"answer": "", "citedChunkIds": [], "sufficient": False}
    chunk_id, text = passages[0]
    return {"answer": f"According to the policy passage: {first_sentence(text)}", "citedChunkIds": [chunk_id],
            "sufficient": True}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        self._send(200 if self.path == "/health" else 404, {"status": "UP"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.endswith("/chat/completions"):
            self._send(404, {"error": {"message": "not found"}})
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            reply = reply_for(request.get("messages", []))
        except (ValueError, TypeError, AttributeError):
            self._send(400, {"error": {"message": "bad request"}})
            return
        self._send(200, {
            "id": "chatcmpl-e2e-stub", "object": "chat.completion", "model": "e2e-llm-stub",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(reply)}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        })

    def log_message(self, fmt: str, *args) -> None:
        print(f"llm-stub {self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    port = int(os.getenv("STUB_PORT", "8443"))
    # Listens on all interfaces because it runs in its own container on the compose network.
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # nosemgrep: avoid-bind-to-all-interfaces
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(os.environ["STUB_CERT"], os.environ["STUB_KEY"])
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"llm-stub listening on https://0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
