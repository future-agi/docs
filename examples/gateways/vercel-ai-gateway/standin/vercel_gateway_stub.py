#!/usr/bin/env python3
"""Local STAND-IN for the Vercel AI Gateway Chat Completions endpoint.

This is NOT Vercel. It is a small HTTP server shaped like the OpenAI-compatible
Chat Completions API that Vercel documents at
https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions
(base URL path /v1, "Authorization: Bearer <key>", SSE streaming ending in
"data: [DONE]", tool calls). Its status codes, error bodies, routes and stream
usage copy what the live gateway (https://ai-gateway.vercel.sh/v1) answered on
2026-10-18. Its reply text is made up, and the routing and cost metadata it
adds are a trimmed copy of the live fields with placeholder values. It exists
so the recipe in ../app.py and its tests can run without a Vercel key or spend.

Behaviour (deterministic, no model is called):

* The reply echoes the last user or tool message, so a unique marker in a
  prompt shows up in the response, in tool-call arguments and in tool results.
* A request that carries "tools" and no "tool" message yet returns one tool
  call whose arguments are {"query": <last user message>}.
* Errors, as the live gateway answered them: no Authorization header or a wrong
  key -> 401 authentication_error; model "does-not-exist/..." -> 404
  model_not_found; a missing "model" -> 400 invalid_request_error; another path
  under /v1 (for example a doubled /v1/v1) -> 404 not_found_error (JSON); a path
  outside /v1 (a base URL without /v1) -> 404 with an HTML page.
* STUB_RESPONSE_MODEL (or --response-model) makes the response "model" differ
  from the requested one, to see what the instrumentor records in that case
  (the live gateway answers a model id sent without its provider prefix with
  the full canonical id).
* "stream": true returns SSE. The finish chunk carries "usage" whether or not
  the request sets stream_options.include_usage, as the live gateway did.

The server records what it received (header names, the Authorization value,
the request body) and serves it at GET /__requests so tests can assert that
Future AGI keys never reach the gateway.
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WORD = " "

# Copied from the live gateway's 401 body for a wrong key (2026-10-18).
AUTH_FAILED = (
    "Authentication failed. Create an API key and set in AI_GATEWAY_API_KEY environment variable: "
    "https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai-gateway%2Fapi-keys%3FshowCreateKeyModal"
)
# The live gateway serves a full HTML page here; this is a short placeholder of the same type.
HTML_404 = "<!DOCTYPE html><html><head><title>404: This page could not be found.</title></head><body>404</body></html>"


def _count_tokens(text):
    return len(str(text).split())


def _message_text(message):
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


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

        def _send_html(self, status, html):
            data = html.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, message, etype, param=None, code=None):
            self._send_json(status, {"error": {"message": message, "type": etype, "param": param, "code": code}})

        def do_GET(self):
            if self.path == "/__requests":
                with stub.lock:
                    return self._send_json(200, stub.requests)
            if self.path == "/healthz":
                return self._send_json(200, {"ok": True})
            self._error(404, "Not found", "invalid_request_error")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {"_unparsed": raw.decode("utf-8", "replace")}
            stub.record(self.path, dict(self.headers.items()), body)
            path = self.path.rstrip("/")
            if not path.startswith("/v1/"):
                # a base URL without /v1: the live gateway answers with its HTML 404 page
                return self._send_html(404, HTML_404)
            auth = self.headers.get("Authorization")
            if not auth:
                return self._send_json(401, {"error": {"message": "Missing Authorization header", "type": "authentication_error"}})
            if auth != f"Bearer {stub.api_key}":
                return self._send_json(401, {"error": {"message": AUTH_FAILED, "type": "authentication_error"}})
            if path != "/v1/chat/completions":
                return self._error(404, f"The requested resource was not found: {path}", "not_found_error", None, "not_found_error")
            model = body.get("model")
            if not model:
                return self._error(
                    400, "Invalid input: expected string, received undefined", "invalid_request_error", "model", "invalid_request_error"
                )
            if str(model).startswith("does-not-exist"):
                return self._send_json(
                    404, {"error": {"message": f"Model '{model}' not found", "type": "model_not_found", "param": {"modelId": model}}}
                )
            return self._complete(body, model)

        def _complete(self, body, model):
            messages = body.get("messages") or []
            last = messages[-1] if messages else {}
            last_text = _message_text(last)
            prompt_tokens = sum(_count_tokens(_message_text(m)) for m in messages) or 1
            response_model = stub.response_model or model
            call_id = f"gen_STUB{int(time.time() * 1000)}"
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
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                # the live gateway adds its cost to usage (placeholder value here)
                "cost": 0.0000012,
                "is_byok": False,
            }
            # The live gateway puts routing and cost metadata on the message and on the last stream
            # delta. Trimmed copy of the field names, placeholder values.
            gateway_meta = {
                "gateway": {
                    "routing": {
                        "originalModelId": model,
                        "resolvedProvider": "example-provider",
                        "finalProvider": "example-provider",
                        "modelAttemptCount": 1,
                    },
                    "cost": "0.0000012",
                    "generationId": call_id,
                }
            }
            message["provider_metadata"] = gateway_meta
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
                        "generationId": call_id,
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

            def event(delta, finish_reason=None, with_usage=None):
                payload = {
                    "id": call_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": response_model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
                    "generationId": call_id,
                }
                if with_usage is not None:
                    payload["usage"] = with_usage
                chunk(json.dumps(payload))

            if wants_tool:
                tc = message["tool_calls"][0]
                event({"role": "assistant", "content": None, "tool_calls": [{"index": 0, "id": tc["id"], "type": "function", "function": {"name": tc["function"]["name"], "arguments": ""}}]})
                event({"tool_calls": [{"index": 0, "function": {"arguments": tc["function"]["arguments"]}}]})
            else:
                words = message["content"].split(WORD)
                event({"role": "assistant", "content": ""})
                for i, w in enumerate(words):
                    event({"content": w if i == 0 else WORD + w})
            # Live: the finish chunk carries usage, with or without stream_options.include_usage.
            event({"provider_metadata": gateway_meta}, finish_reason=finish, with_usage=usage)
            chunk("[DONE]")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            self.close_connection = True

    return Handler


def serve(host="127.0.0.1", port=0, api_key="stub-gateway-key", response_model=None):
    stub = Stub(api_key, response_model)
    server = ThreadingHTTPServer((host, port), make_handler(stub))
    server.stub = stub
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--api-key", default=os.environ.get("STUB_API_KEY", "stub-gateway-key"))
    ap.add_argument("--response-model", default=os.environ.get("STUB_RESPONSE_MODEL"))
    a = ap.parse_args()
    server = serve(a.host, a.port, a.api_key, a.response_model)
    print(f"STAND-IN for Vercel AI Gateway listening on http://{a.host}:{server.server_address[1]}/v1 (not Vercel)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
