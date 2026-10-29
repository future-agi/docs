"""A deterministic stand-in for an OpenAI-compatible Chat Completions endpoint (tests only).

It is NOT a model. First turn: it asks for ``get_weather`` with the first word of the
user's question that looks like ``MARK-...`` as the city (else ``Lisbon``). After a tool
result: it answers and repeats the question. Usage is always 17 prompt / 5 completion
tokens. A wrong bearer key gets a 401 like OpenAI's.

usage: python fake_openai.py --port PORT --api-key KEY
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROMPT_TOKENS, COMPLETION_TOKENS = 17, 5


def _reply(body: dict) -> dict:
    messages = body.get("messages", [])
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    if isinstance(user, list):
        user = " ".join(part.get("text", "") for part in user if isinstance(part, dict))
    if any(m.get("role") == "tool" for m in messages) or not body.get("tools"):
        message = {"role": "assistant", "content": f"It is sunny. You asked: {user}"}
        finish = "stop"
    else:
        match = re.search(r"MARK-[0-9a-f]+", user)
        city = match.group(0) if match else "Lisbon"
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_0001",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": json.dumps({"city": city})},
                }
            ],
        }
        finish = "tool_calls"
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 1,
        "model": body.get("model", "fake-model"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": PROMPT_TOKENS,
            "completion_tokens": COMPLETION_TOKENS,
            "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
        },
    }


def make_server(api_key: str, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.headers.get("Authorization", "") != f"Bearer {api_key}":
                self._json(401, {"error": {"message": "Invalid API key", "type": "invalid_request_error"}})
                return
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._json(404, {"error": {"message": "not found"}})
                return
            reply = _reply(body)
            if body.get("stream"):
                self._stream(reply)
            else:
                self._json(200, reply)

        def _json(self, code: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _stream(self, reply: dict) -> None:
            choice = reply["choices"][0]
            delta = {k: v for k, v in choice["message"].items() if v is not None}
            if "tool_calls" in delta:
                delta["tool_calls"] = [dict(tc, index=0) for tc in delta["tool_calls"]]
            chunks = [
                {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}]},
                {"choices": [], "usage": reply["usage"]},
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in chunks:
                chunk.update(id=reply["id"], object="chat.completion.chunk", created=1, model=reply["model"])
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *_args) -> None:
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


class FakeOpenAI:
    """Run the stand-in in a background thread: ``with FakeOpenAI(key) as fake: fake.url``."""

    def __init__(self, api_key: str) -> None:
        self._server = make_server(api_key)
        self.url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeOpenAI":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--api-key", required=True)
    args = parser.parse_args()
    make_server(args.api_key, args.port).serve_forever()
