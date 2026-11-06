#!/usr/bin/env python3
"""Local STAND-IN for the CometAPI chat completions endpoint.

This is NOT CometAPI. It is a small HTTP server shaped like the endpoint that
CometAPI documents at
https://apidoc.cometapi.com/api/text/chat (`POST /v1/chat/completions`,
`Authorization: Bearer $COMETAPI_KEY`, the documented response fields, SSE
chunks that end with `data: [DONE]`) and the error envelope on
https://apidoc.cometapi.com/errors/error-codes-handling. It exists so the
recipe in ../app.py can be exercised without a CometAPI account, an API key or
any spend. Nothing here was captured from a real CometAPI response. Fields the
documentation lists are produced; fields it does not list are not.

Behaviour (deterministic, no model is called):

* The reply echoes the last user or tool message, so a unique marker in a
  prompt shows up in the response, in tool-call arguments and in tool results.
* A request that carries "tools" and no "tool" message yet returns one tool
  call whose arguments are {"query": <last user message>}.
* A wrong bearer token returns 401 with the documented envelope
  {"error": {"message": "invalid token (request id: ...)", "type":
  "comet_api_error", "code": ""}}. A missing `model` returns 400 with
  "model name is required (request id: ...)", as the chat page's 400 example.
* "stream": true returns SSE. A usage chunk (empty `choices`, full `usage`) is
  added before `[DONE]` only when `stream_options.include_usage` is true, as
  the chat page documents. Without it no chunk carries usage.
* Any path other than /v1/chat/completions answers 404 with the same envelope.
  This is the stand-in's choice. CometAPI's own pages disagree about what a
  wrong base URL looks like (its base-URL guide says 404, its error-handling
  page says it "may show up as a 301 redirect or HTML, not a clean JSON 404"),
  and neither was reproduced against CometAPI.

The server records what it received (header names, the Authorization value,
the request body) and serves it at GET /__requests so tests can assert that
Future AGI keys never reach CometAPI.
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHAT_PATH = "/v1/chat/completions"
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
    return f"{int(time.time() * 1000):013d}{counter[0]:04d}stub"


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

        def _error(self, status, message, code=""):
            rid = request_id()
            self._send_json(
                status,
                {"error": {"code": code, "message": f"{message} (request id: {rid})", "type": "comet_api_error"}},
            )

        def do_GET(self):
            if self.path == "/__requests":
                with stub.lock:
                    return self._send_json(200, stub.requests)
            if self.path == "/healthz":
                return self._send_json(200, {"ok": True})
            self._error(404, "not found")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {"_unparsed": raw.decode("utf-8", "replace")}
            stub.record(self.path, dict(self.headers.items()), body)
            if self.headers.get("Authorization") != f"Bearer {stub.api_key}":
                return self._error(401, "invalid token")
            if self.path.rstrip("/") != CHAT_PATH:
                return self._error(404, "not found")
            model = body.get("model")
            if not model:
                return self._error(400, "model name is required")
            return self._complete(body, model)

        def _complete(self, body, model):
            messages = body.get("messages") or []
            last = messages[-1] if messages else {}
            last_text = _message_text(last)
            prompt_tokens = sum(_count_tokens(_message_text(m)) for m in messages) or 1
            response_model = stub.response_model or model
            call_id = "chatcmpl_" + request_id()
            created = int(time.time())
            wants_tool = bool(body.get("tools")) and last.get("role") != "tool"
            if wants_tool:
                message = {
                    "role": "assistant",
                    "content": None,
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
            usage = {
                "completion_tokens": completion_tokens,
                "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0,
                },
                "prompt_tokens": prompt_tokens,
                "prompt_tokens_details": {"audio_tokens": 0, "cache_write_tokens": 0, "cached_tokens": 0},
                "total_tokens": prompt_tokens + completion_tokens,
            }
            if not body.get("stream"):
                return self._send_json(
                    200,
                    {
                        "id": call_id,
                        "object": "chat.completion",
                        "created": created,
                        "model": response_model,
                        "choices": [{"index": 0, "message": message, "finish_reason": finish, "logprobs": None}],
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
                payload = {
                    "choices": (
                        [{"delta": delta, "finish_reason": finish_reason, "index": 0, "logprobs": None}] if choices else []
                    ),
                    "created": created,
                    "id": call_id,
                    "model": response_model,
                    "object": "chat.completion.chunk",
                }
                if usage_value is not None:
                    payload["usage"] = usage_value
                chunk(json.dumps(payload))

            if wants_tool:
                tc = message["tool_calls"][0]
                event(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": tc["id"],
                                "type": "function",
                                "function": {"name": tc["function"]["name"], "arguments": ""},
                            }
                        ],
                    }
                )
                event({"tool_calls": [{"index": 0, "function": {"arguments": tc["function"]["arguments"]}}]})
            else:
                words = message["content"].split(WORD)
                event({"content": "", "refusal": None, "role": "assistant"})
                for i, w in enumerate(words):
                    event({"content": w if i == 0 else WORD + w})
            event({}, finish_reason=finish)
            if (body.get("stream_options") or {}).get("include_usage"):
                event(None, usage_value=usage, choices=False)
            chunk("[DONE]")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            self.close_connection = True

    return Handler


def serve(host="127.0.0.1", port=0, api_key="stub-cometapi-key", response_model=None):
    stub = Stub(api_key, response_model)
    server = ThreadingHTTPServer((host, port), make_handler(stub))
    server.stub = stub
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8789)
    ap.add_argument("--api-key", default=os.environ.get("STUB_API_KEY", "stub-cometapi-key"))
    ap.add_argument("--response-model", default=os.environ.get("STUB_RESPONSE_MODEL"))
    a = ap.parse_args()
    server = serve(a.host, a.port, a.api_key, a.response_model)
    print(
        f"STAND-IN for CometAPI listening on http://{a.host}:{server.server_address[1]}/v1 (not CometAPI)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
