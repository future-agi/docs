#!/usr/bin/env python3
"""Local STAND-IN for Novita AI's OpenAI-compatible chat completions route.

This is NOT Novita. It is a small HTTP server shaped like the route that Novita documents at
https://docs.novita.ai/api-reference/model-apis-llm-create-chat-completion and
https://docs.novita.ai/guides/quickstart (`POST .../openai/v1/chat/completions`,
`Authorization: Bearer <key>`, the documented response fields, SSE chunks that end with
`data: [DONE]`). It lets the tests in ../tests exercise the recipe without a Novita key or spend.

The status codes, error bodies, routes and streaming usage below match what the live API at
api.novita.ai returned on 2026-10-18 (meta-llama/llama-3.1-8b-instruct). The reply text and token
counts are made up: no model is called.

* Routes. The live API answered 200 on all three base URL forms that appear in Novita's and
  Langfuse's pages: `/openai/v1/chat/completions` (the recipe), `/openai/chat/completions`
  (`base_url="https://api.novita.ai/openai"`) and `/v3/openai/chat/completions` (Langfuse's
  string). The stand-in serves all three by default; pass `paths=` to serve fewer. Any other path
  answers 404 with the plain-text body `404 page not found`, as the live API did for
  `/chat/completions`, `/v1/chat/completions` and `/openai/v1/v1/chat/completions`.
* The reply echoes the last user or tool message, so a unique marker in a prompt shows up in the
  response, in tool-call arguments and in tool results.
* A request that carries "tools" and no "tool" message yet returns one tool call whose arguments
  are {"query": <last user message>}. The id is "0", as in Novita's function-calling guide.
* usage has the three documented fields (prompt_tokens, completion_tokens, total_tokens).
* "stream": true returns SSE. A usage chunk (empty `choices`, full `usage`) comes before
  `[DONE]` whether or not `stream_options.include_usage` is set: the live API sent it in both cases.
* Errors use the envelope the live API returned, `{code, reason, message, metadata}`:
  a wrong key is 401 `FAILED_TO_AUTH` "failed to authenticate API key" with empty metadata; a
  missing or unknown model id is 404 `MODEL_NOT_FOUND` "model not found" with
  `metadata.reason` "model: <id> not found". The stand-in treats the ids in `unknown_models`
  (default: UNKNOWN_MODEL) as unknown and accepts every other id.

The server records what it received (header names, the Authorization value, the request path and
body) and serves it at GET /__requests so tests can assert that Future AGI keys never reach Novita.
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

V1_PATH = "/openai/v1/chat/completions"
BARE_PATH = "/openai/chat/completions"
V3_PATH = "/v3/openai/chat/completions"
DEFAULT_PATHS = (V1_PATH, BARE_PATH, V3_PATH)
# A model id the stand-in answers with 404 MODEL_NOT_FOUND (the app's bad-model scenario uses it).
UNKNOWN_MODEL = "novita-ai-example/no-such-model"
WORD = " "


def _count_tokens(text):
    return len(str(text).split())


def _message_text(message):
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def next_id(counter=[0]):
    counter[0] += 1
    return f"{int(time.time() * 1000):013d}{counter[0]:04d}00000000"


class Stub:
    def __init__(self, api_key, paths=DEFAULT_PATHS, response_model=None, unknown_models=(UNKNOWN_MODEL,)):
        self.api_key = api_key
        self.paths = tuple(paths)
        self.response_model = response_model
        self.unknown_models = set(unknown_models)
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

        def _error(self, status, reason, message, metadata=None):
            self._send_json(status, {"code": status, "reason": reason, "message": message, "metadata": metadata or {}})

        def _not_found(self):
            data = b"404 page not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/__requests":
                with stub.lock:
                    return self._send_json(200, stub.requests)
            if self.path == "/healthz":
                return self._send_json(200, {"ok": True})
            self._not_found()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {"_unparsed": raw.decode("utf-8", "replace")}
            stub.record(self.path, dict(self.headers.items()), body)
            if self.path.rstrip("/") not in stub.paths:
                return self._not_found()
            if self.headers.get("Authorization") != f"Bearer {stub.api_key}":
                return self._error(401, "FAILED_TO_AUTH", "failed to authenticate API key")
            model = body.get("model") or ""
            if not model or model in stub.unknown_models:
                return self._error(404, "MODEL_NOT_FOUND", "model not found", {"reason": f"model: {model} not found"})
            return self._complete(body, model)

        def _complete(self, body, model):
            messages = body.get("messages") or []
            last = messages[-1] if messages else {}
            last_text = _message_text(last)
            prompt_tokens = sum(_count_tokens(_message_text(m)) for m in messages) or 1
            response_model = stub.response_model or model
            call_id = "chatcmpl-" + next_id()
            created = int(time.time())
            wants_tool = bool(body.get("tools")) and last.get("role") != "tool"
            if wants_tool:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "0",
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
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
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
                        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
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
                    "choices": ([{"delta": delta, "finish_reason": finish_reason, "index": 0}] if choices else []),
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
                event({"role": "assistant", "content": ""})
                for i, w in enumerate(words):
                    event({"content": w if i == 0 else WORD + w})
            event({}, finish_reason=finish)
            event(None, usage_value=usage, choices=False)  # sent with or without stream_options, as live
            chunk("[DONE]")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            self.close_connection = True

    return Handler


def serve(host="127.0.0.1", port=0, api_key="stub-novita-key", paths=DEFAULT_PATHS, response_model=None,
          unknown_models=(UNKNOWN_MODEL,)):
    stub = Stub(api_key, paths, response_model, unknown_models)
    server = ThreadingHTTPServer((host, port), make_handler(stub))
    server.stub = stub
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--api-key", default=os.environ.get("STUB_API_KEY", "stub-novita-key"))
    ap.add_argument("--response-model", default=os.environ.get("STUB_RESPONSE_MODEL"))
    ap.add_argument(
        "--only",
        choices=["v1", "bare", "v3"],
        help="serve only /openai/v1/... (v1), /openai/... (bare) or /v3/openai/... (v3); default serves all three",
    )
    a = ap.parse_args()
    paths = {"v1": (V1_PATH,), "bare": (BARE_PATH,), "v3": (V3_PATH,)}.get(a.only, DEFAULT_PATHS)
    server = serve(a.host, a.port, a.api_key, paths, a.response_model)
    print(
        f"STAND-IN for Novita listening on http://{a.host}:{server.server_address[1]}/openai/v1 (not Novita); "
        f"serving {', '.join(paths)}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
