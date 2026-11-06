#!/usr/bin/env python3
"""A tiny OpenAI-compatible chat upstream for testing LiteLLM Proxy without spending anything.

Stdlib only. It answers POST /v1/chat/completions (plain, streaming, tool calls and
errors) and GET /v1/models, and it counts what it received so a test can assert that
a request really went through the proxy to the upstream.

Behaviour is driven by the request, so one process covers every case:

* A user message containing a token like ``MARK_abc123`` is echoed back in the reply
  (and in tool-call arguments). Tests use it as a unique marker to look for in exports.
* ``tools`` present and no ``tool`` message yet: the reply is a ``tool_calls`` response
  for the first tool, with the marker as its argument.
* A ``tool`` message present: the reply is the final answer, containing the marker.
* A user message containing ``FAIL_UPSTREAM``: HTTP 500 with a fixed error body that
  contains ``UPSTREAM_ERROR_MARKER_7f3a`` (so a test can check raw provider error text).
* ``stream: true``: server-sent events; the last chunk carries usage when the request
  sets ``stream_options.include_usage``.

Usage:  python3 mock_upstream.py --port 18081
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ERROR_MARKER = "UPSTREAM_ERROR_MARKER_7f3a"
MARK_RE = re.compile(r"MARK_[A-Za-z0-9]+")


def _text_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def find_marker(messages: list) -> str:
    for message in reversed(messages):
        found = MARK_RE.search(_text_of(message))
        if found:
            return found.group(0)
    return "MARK_none"


def build_reply(body: dict) -> dict:
    """Return {'message': {...}, 'finish_reason': str} for a chat request body."""
    messages = body.get("messages") or []
    marker = find_marker(messages)
    tools = body.get("tools") or []
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    if tools and not has_tool_result:
        name = (tools[0].get("function") or {}).get("name", "lookup")
        return {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_mock_1",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps({"query": marker})},
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    prefix = "final answer" if has_tool_result else "mock reply"
    return {
        "message": {"role": "assistant", "content": f"{prefix} for {marker}"},
        "finish_reason": "stop",
    }


def usage_for(body: dict, reply: dict) -> dict:
    prompt_chars = sum(len(_text_of(m)) for m in body.get("messages") or [])
    completion_chars = len(reply["message"].get("content") or "") + len(
        json.dumps(reply["message"].get("tool_calls") or "")
    )
    prompt = max(1, prompt_chars // 4)
    completion = max(1, completion_chars // 4)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests = 0
        self.last_body: dict | None = None
        self.last_headers: dict = {}


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep the console quiet
            return

        def _send_json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") in ("/v1/models", "/models"):
                self._send_json(200, {"object": "list", "data": [{"id": "mock-model", "object": "model"}]})
            elif self.path == "/health":
                self._send_json(200, {"ok": True, "requests": state.requests})
            else:
                self._send_json(404, {"error": {"message": "not found"}})

        def do_POST(self):  # noqa: N802
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._send_json(404, {"error": {"message": "not found"}})
                return
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size) or b"{}")
            with state.lock:
                state.requests += 1
                state.last_body = body
                state.last_headers = {k.lower(): v for k, v in self.headers.items()}
            messages = body.get("messages") or []
            if any("FAIL_UPSTREAM" in _text_of(m) for m in messages):
                self._send_json(
                    500,
                    {"error": {"message": f"mock upstream failure {ERROR_MARKER}", "type": "server_error"}},
                )
                return
            reply = build_reply(body)
            usage = usage_for(body, reply)
            model = body.get("model", "mock-model")
            created = int(time.time())
            if body.get("stream"):
                self._stream(body, reply, usage, model, created)
                return
            self._send_json(
                200,
                {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "message": reply["message"], "finish_reason": reply["finish_reason"]}],
                    "usage": usage,
                },
            )

        def _stream(self, body, reply, usage, model, created):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def chunk(payload: dict) -> None:
                line = b"data: " + json.dumps(payload).encode() + b"\n\n"
                self.wfile.write(f"{len(line):x}\r\n".encode() + line + b"\r\n")
                self.wfile.flush()

            def base(delta: dict, finish=None, with_usage=None) -> dict:
                out = {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}] if with_usage is None else [],
                }
                if with_usage is not None:
                    out["usage"] = with_usage
                return out

            message = reply["message"]
            chunk(base({"role": "assistant", "content": ""}))
            if message.get("tool_calls"):
                call = message["tool_calls"][0]
                chunk(base({"tool_calls": [{"index": 0, **call}]}))
            else:
                for word in (message.get("content") or "").split(" "):
                    chunk(base({"content": word + " "}))
            chunk(base({}, finish=reply["finish_reason"]))
            if (body.get("stream_options") or {}).get("include_usage"):
                chunk(base({}, with_usage=usage))
            done = b"data: [DONE]\n\n"
            self.wfile.write(f"{len(done):x}\r\n".encode() + done + b"\r\n0\r\n\r\n")
            self.wfile.flush()

    return Handler


def serve(host: str, port: int) -> tuple[ThreadingHTTPServer, State]:
    state = State()
    server = ThreadingHTTPServer((host, port), make_handler(state))
    return server, state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    server, _ = serve(args.host, args.port)
    print(f"mock upstream listening on http://{args.host}:{args.port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
