#!/usr/bin/env python3
"""Local STAND-IN for the Z.ai general platform Chat Completions API.

This is NOT Z.ai. It is a small HTTP server shaped like the API that Z.ai
documents at https://docs.z.ai/api-reference/llm/chat-completion
(`POST /api/paas/v4/chat/completions`, `Authorization: Bearer <ZAI_API_KEY>`),
https://docs.z.ai/guides/capabilities/streaming (SSE chunks, `usage` on the last
chunk, `data: [DONE]`) and https://docs.z.ai/api-reference/api-code (error codes
and the `{"error": {"code", "message"}}` shape), all read 2026-10-15. It exists
so the recipe in ../app.py can be exercised without a Z.ai account, a key or any
spend. Nothing here was captured from a real Z.ai response. Fields the
documentation lists are produced; fields it does not list are not.

Behaviour (deterministic, no model is called):

* The reply echoes the last user or tool message, so a unique marker in a prompt
  shows up in the response, in tool-call arguments and in tool results.
* A request that carries "tools" and no "tool" message yet returns one tool call
  whose arguments are {"query": <last user message>}. Z.ai documents only
  `tool_choice: "auto"`; any other value is answered with error 1214.
* `thinking.type == "enabled"` adds `reasoning_content` to the message (or to the
  stream deltas), as the Z.ai docs describe.
* A wrong bearer token returns 401 with business code 1000; no Authorization
  header returns 401 with code 1001; a model name that does not start with
  "glm-" returns 400 with code 1211. The messages are the ones in Z.ai's error
  table; the exact body for each case on the live API was not checked.
* A streamed request whose last user message contains `[[abnormal-stream]]` stops after two words
  and ends with `finish_reason: "network_error"` instead of an HTTP error, which is how Z.ai
  documents an inference that terminates abnormally during a stream (docs.z.ai/api-reference/api-code).
* "stream": true returns SSE exactly like the Z.ai example: no `object` field,
  `finish_reason` and `usage` on the final chunk (no `stream_options` needed),
  then `data: [DONE]`. `--with-object` adds the OpenAI `object` field to every
  response and chunk, in case the live API includes it.

The server records what it received and serves it at GET /__requests so tests
can assert that Future AGI keys never reach Z.ai.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHAT_PATH = "/api/paas/v4/chat/completions"
ERRORS = {
    "1000": (401, "Authentication Failed"),
    "1001": (401, "Authentication parameter not received in Header, unable to authenticate"),
    "1211": (400, "Unknown Model, please check the model code."),
    "1214": (400, "Parameter `tool_choice` is invalid. Please check the documentation."),
}


def _count_tokens(text):
    return len(str(text).split())


def _message_text(message):
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


class Stub:
    def __init__(self, api_key, with_object=False):
        self.api_key = api_key
        self.with_object = with_object
        self.requests = []
        self.lock = threading.Lock()
        self.counter = 0

    def next_id(self):
        with self.lock:
            self.counter += 1
            return self.counter

    def record(self, path, headers, body):
        lowered = {k.lower(): v for k, v in headers.items()}
        auth = lowered.get("authorization") or ""
        with self.lock:
            self.requests.append(
                {
                    "path": path,
                    "header_names": sorted(lowered),
                    "authorization_scheme": auth.split(" ", 1)[0] if auth else None,
                    "authorization_matches": auth == f"Bearer {self.api_key}",
                    "body": body,
                }
            )


def _plan(body):
    """What the stub answers: ('tool', args) or ('text', reply, reasoning)."""
    messages = body.get("messages") or []
    last = messages[-1] if messages else {}
    text = _message_text(last)
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    thinking = (body.get("thinking") or {}).get("type") == "enabled"
    if body.get("tools") and not has_tool_result:
        return ("tool", {"query": text}, None)
    if last.get("role") == "tool":
        reply = f"The lookup returned: {text}"
    else:
        reply = f"Z.ai stand-in reply to: {text}"
    reasoning = f"Stand-in reasoning about: {text}" if thinking else None
    return ("text", reply, reasoning)


def _usage(body, plan):
    prompt = sum(_count_tokens(_message_text(m)) for m in body.get("messages") or []) or 1
    if plan[0] == "tool":
        completion = _count_tokens(json.dumps(plan[1]))
    else:
        completion = _count_tokens(plan[1]) + (_count_tokens(plan[2]) if plan[2] else 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "prompt_tokens_details": {"cached_tokens": 0},
        "total_tokens": prompt + completion,
    }


def build_response(stub, body, n):
    plan = _plan(body)
    message = {"role": "assistant"}
    if plan[0] == "tool":
        message["content"] = ""
        message["tool_calls"] = [
            {
                "id": f"call_{n}",
                "type": "function",
                "index": 0,
                "function": {"name": body["tools"][0]["function"]["name"], "arguments": json.dumps(plan[1])},
            }
        ]
        finish = "tool_calls"
    else:
        message["content"] = plan[1]
        if plan[2]:
            message["reasoning_content"] = plan[2]
        finish = "stop"
    out = {
        "id": str(n),
        "request_id": f"stub-req-{n:06d}",
        "created": int(time.time()),
        "model": body.get("model"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": _usage(body, plan),
    }
    if stub.with_object:
        out["object"] = "chat.completion"
    return out


def build_stream(stub, body, n):
    plan = _plan(body)
    base = {"id": str(n), "created": int(time.time()), "model": body.get("model")}
    if stub.with_object:
        base["object"] = "chat.completion.chunk"
    chunks = []

    def chunk(delta, finish=None, usage=None):
        c = dict(base)
        c["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish}] if finish is None else [
            {"index": 0, "finish_reason": finish, "delta": delta}
        ]
        if usage is not None:
            c["usage"] = usage
        return c

    if plan[0] == "tool":
        call = {
            "id": f"call_{n}",
            "type": "function",
            "index": 0,
            "function": {"name": body["tools"][0]["function"]["name"], "arguments": json.dumps(plan[1])},
        }
        chunks.append(chunk({"role": "assistant", "content": "", "tool_calls": [call]}))
        final_delta, finish = {"role": "assistant", "content": ""}, "tool_calls"
    else:
        if plan[2]:
            for word in plan[2].split(" "):
                chunks.append(chunk({"reasoning_content": word + " "}))
        words = plan[1].split(" ")
        abnormal = "[[abnormal-stream]]" in _message_text((body.get("messages") or [{}])[-1])
        if abnormal:
            words = words[:2]
        for i, word in enumerate(words):
            chunks.append(chunk({"content": word + (" " if i < len(words) - 1 else "")}))
        final_delta, finish = {"role": "assistant", "content": ""}, ("network_error" if abnormal else "stop")
    chunks.append(chunk(final_delta, finish=finish, usage=_usage(body, plan)))
    return chunks


def make_handler(stub):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, status, payload, content_type="application/json"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, code):
            status, message = ERRORS[code]
            self._send(status, {"error": {"code": code, "message": message}})

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, {"ok": True})
            if self.path == "/__requests":
                with stub.lock:
                    return self._send(200, list(stub.requests))
            self._send(404, {"error": {"code": "1222", "message": "API `x` does not exist"}})

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            stub.record(self.path, self.headers, body)
            if self.path != CHAT_PATH:
                return self._send(404, {"error": {"code": "1222", "message": f"API `{self.path}` does not exist"}})
            auth = self.headers.get("Authorization")
            if not auth:
                return self._error("1001")
            if auth != f"Bearer {stub.api_key}":
                return self._error("1000")
            if not str(body.get("model", "")).startswith("glm-"):
                return self._error("1211")
            if body.get("tool_choice") not in (None, "auto"):
                return self._error("1214")
            n = stub.next_id()
            if not body.get("stream"):
                return self._send(200, build_response(stub, body, n))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=UTF-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def write(data):
                self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")

            for c in build_stream(stub, body, n):
                write(f"data: {json.dumps(c)}\n\n".encode())
            write(b"data: [DONE]\n\n")
            self.wfile.write(b"0\r\n\r\n")

    return Handler


def serve(api_key, host="127.0.0.1", port=0, with_object=False):
    stub = Stub(api_key, with_object=with_object)
    server = ThreadingHTTPServer((host, port), make_handler(stub))
    server.daemon_threads = True
    server.stub = stub
    return server


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--api-key", default="e2e-stand-in-key")
    ap.add_argument("--with-object", action="store_true", help="add the OpenAI `object` field to responses and chunks")
    a = ap.parse_args(argv)
    server = serve(a.api_key, port=a.port, with_object=a.with_object)
    print(f"http://127.0.0.1:{server.server_address[1]}/api/paas/v4/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
