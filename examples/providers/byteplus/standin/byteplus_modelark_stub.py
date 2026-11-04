#!/usr/bin/env python3
"""Local STAND-IN for the BytePlus ModelArk Chat API.

This is NOT BytePlus. It is a small HTTP server shaped like the Chat API that
BytePlus documents at
https://ai.byteplus.com/ark/region:ap-southeast-1/docs/chat-api
(`POST /api/v3/chat/completions`, `Authorization: Bearer <ARK_API_KEY>`, the
documented response fields, SSE chunks that end with `data: [DONE]`, and the
error codes table at .../docs/error-codes). It exists so the recipe in
../app.py can be exercised without a BytePlus account, an API key or any
spend. Nothing here was captured from a real BytePlus response. Fields the
documentation lists are produced; fields it does not list are not.

Behaviour (deterministic, no model is called):

* The reply echoes the last user or tool message, so a unique marker in a
  prompt shows up in the response, in tool-call arguments and in tool results.
* A request that carries "tools" and no "tool" message yet returns one tool
  call whose arguments are {"query": <last user message>}.
* `thinking.type` other than "disabled" adds `reasoning_content` (and
  `completion_tokens_details.reasoning_tokens`) to the response, as the Chat
  API documents for models that support deep reasoning. "disabled" omits it.
* A wrong bearer token returns 401 / AuthenticationError, an unknown model
  (name starting with "does-not-exist") returns 404 /
  InvalidEndpointOrModel.NotFound. Both use the code, type and message from
  BytePlus's error-codes table. The `{"error": {code, message, param, type}}`
  envelope is NOT shown on the pages that were read; it is an assumption
  (OpenAI-style) and the recipe does not depend on it.
* "stream": true returns SSE. A usage chunk (empty `choices`, full `usage`) is
  added before `[DONE]` only when `stream_options.include_usage` is true, as
  the Chat API documents. Without it every chunk carries `"usage": null`.

The server records what it received (header names, the Authorization value,
the request body) and serves it at GET /__requests so tests can assert that
Future AGI keys never reach BytePlus.
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHAT_PATH = "/api/v3/chat/completions"
WORD = " "


def _count_tokens(text):
    return len(str(text).split())


def _message_text(message):
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def request_id(counter=[0]):
    counter[0] += 1
    # BytePlus request ids in the docs look like "0217426318107460cfa43dc3f3683b1de1c09624ff49085a456ac"
    return f"02{int(time.time() * 1000):013d}{counter[0]:04d}stub"


class Stub:
    def __init__(self, api_key, response_model=None):
        self.api_key = api_key
        self.response_model = response_model
        self.requests = []
        self.lock = threading.Lock()

    def record(self, path, headers, body):
        lowered = {k.lower(): v for k, v in headers.items()}
        with self.lock:
            self.requests.append(
                {
                    "path": path,
                    "header_names": sorted(lowered),
                    "authorization": lowered.get("authorization"),
                    "headers": lowered,
                    "body": body,
                }
            )


def make_handler(stub):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep test output quiet
            pass

        def _send_json(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, code, etype, message):
            rid = request_id()
            self._send_json(
                status,
                {"error": {"code": code, "message": f"{message} Request id: {rid}", "param": "", "type": etype}},
            )

        def do_GET(self):
            if self.path == "/__requests":
                with stub.lock:
                    return self._send_json(200, stub.requests)
            if self.path == "/healthz":
                return self._send_json(200, {"ok": True})
            self._error(404, "NotFound", "NotFound", "The requested resource does not exist.")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {"_unparsed": raw.decode("utf-8", "replace")}
            stub.record(self.path, dict(self.headers.items()), body)
            if self.headers.get("Authorization") != f"Bearer {stub.api_key}":
                return self._error(
                    401, "AuthenticationError", "Unauthorized", "The API key or AK/SK in the request is missing or invalid."
                )
            if self.path.rstrip("/") != CHAT_PATH:
                return self._error(404, "NotFound", "NotFound", "The requested resource does not exist.")
            model = body.get("model")
            if not model:
                return self._error(
                    400,
                    "MissingParameter",
                    "BadRequest",
                    "The request failed because it is missing one or multiple required parameters.",
                )
            if str(model).startswith("does-not-exist"):
                return self._error(
                    404,
                    "InvalidEndpointOrModel.NotFound",
                    "NotFound",
                    f"The model or endpoint {model} does not exist or you do not have access to it.",
                )
            return self._complete(body, model)

        def _complete(self, body, model):
            messages = body.get("messages") or []
            last = messages[-1] if messages else {}
            last_text = _message_text(last)
            prompt_tokens = sum(_count_tokens(_message_text(m)) for m in messages) or 1
            response_model = stub.response_model or model
            call_id = request_id()
            created = int(time.time())
            thinking = (body.get("thinking") or {}).get("type")
            reasons = thinking is not None and thinking != "disabled"
            reasoning = "Reasoning about the request before answering." if reasons else None
            reasoning_tokens = _count_tokens(reasoning) if reasoning else 0
            wants_tool = bool(body.get("tools")) and last.get("role") != "tool"
            if wants_tool:
                message = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_stub_1",
                            "type": "function",
                            "function": {
                                "name": body["tools"][0]["function"]["name"],
                                "arguments": json.dumps({"query": last_text}),
                            },
                        }
                    ],
                }
                finish, completion_tokens = "tool_calls", 6
            else:
                message = {"role": "assistant", "content": f"echo: {last_text}"}
                finish, completion_tokens = "stop", _count_tokens(message["content"])
            if reasoning:
                message["reasoning_content"] = reasoning
            completion_tokens += reasoning_tokens
            usage = {
                "completion_tokens": completion_tokens,
                "prompt_tokens": prompt_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "prompt_tokens_details": {"cached_tokens": 0},
                "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
            }
            if not body.get("stream"):
                return self._send_json(
                    200,
                    {
                        "choices": [{"finish_reason": finish, "index": 0, "logprobs": None, "message": message}],
                        "created": created,
                        "id": call_id,
                        "model": response_model,
                        "service_tier": "default",
                        "object": "chat.completion",
                        "usage": usage,
                    },
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def chunk(payload):
                data = ("data: " + payload + "\n\n").encode()
                self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()

            def event(delta, finish_reason=None, usage_value=None, choices=True):
                choice = {"delta": delta, "index": 0}
                if finish_reason:
                    choice["finish_reason"] = finish_reason
                payload = {
                    "choices": [choice] if choices else [],
                    "created": created,
                    "id": call_id,
                    "model": response_model,
                    "service_tier": "default",
                    "object": "chat.completion.chunk",
                    "usage": usage_value,
                }
                chunk(json.dumps(payload))

            if reasoning:
                event({"content": "", "reasoning_content": reasoning, "role": "assistant"})
            if wants_tool:
                tc = message["tool_calls"][0]
                event({"role": "assistant", "content": "", "tool_calls": [{"index": 0, "id": tc["id"], "type": "function", "function": {"name": tc["function"]["name"], "arguments": ""}}]})
                event({"tool_calls": [{"index": 0, "function": {"arguments": tc["function"]["arguments"]}}]})
            else:
                words = message["content"].split(WORD)
                event({"content": "", "role": "assistant"})
                for i, w in enumerate(words):
                    event({"content": w if i == 0 else WORD + w, "role": "assistant"})
            event({"content": "", "role": "assistant"}, finish_reason=finish)
            if (body.get("stream_options") or {}).get("include_usage"):
                event(None, usage_value=usage, choices=False)
            chunk("[DONE]")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            self.close_connection = True

    return Handler


def serve(host="127.0.0.1", port=0, api_key="stub-ark-key", response_model=None):
    stub = Stub(api_key, response_model)
    server = ThreadingHTTPServer((host, port), make_handler(stub))
    server.stub = stub
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8789)
    ap.add_argument("--api-key", default=os.environ.get("STUB_API_KEY", "stub-ark-key"))
    ap.add_argument("--response-model", default=os.environ.get("STUB_RESPONSE_MODEL"))
    a = ap.parse_args()
    server = serve(a.host, a.port, a.api_key, a.response_model)
    print(
        f"STAND-IN for BytePlus ModelArk listening on http://{a.host}:{server.server_address[1]}/api/v3 (not BytePlus)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
