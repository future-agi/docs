"""A small OpenAI Chat Completions server for the tests. Not OpenAI.

Deterministic behaviour, enough for AgentScope's OpenAIChatModel:

* a request that offers tools and has no tool result yet gets one tool call, to the first
  tool offered, with arguments ``{"<first required property>": TOOL_ARG}``;
* a request that already has a tool result gets a text answer that repeats that result;
* any other request gets a text answer that repeats the first user message (AgentScope
  appends a time reminder as a later user message, which is not the prompt);
* model ``model-that-does-not-exist`` gets HTTP 400 with an error body that contains the
  first user message (so the tests can look for it in exported error text);
* ``stream: true`` answers with server-sent events, ending with a usage chunk when
  ``stream_options.include_usage`` is set; otherwise one JSON body with ``usage``.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROMPT_TOKENS = 31
COMPLETION_TOKENS = 7


class FakeOpenAI:
    def __init__(self, api_key: str, tool_arg: str = "Paris", port: int = 0) -> None:
        self.api_key = api_key
        self.tool_arg = tool_arg
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # silence
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
                if self.headers.get("Authorization") != f"Bearer {outer.api_key}":
                    return self._json(401, {"error": {"message": "bad key", "type": "invalid_request_error"}})
                if not self.path.endswith("/chat/completions"):
                    return self._json(404, {"error": {"message": "not found"}})
                outer._chat(self, body)

            def _json(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()

    # ------------------------------------------------------------------
    def _chat(self, h: BaseHTTPRequestHandler, body: dict) -> None:
        messages = body.get("messages", [])
        last_user = next((m for m in messages if m.get("role") == "user"), {})
        user_text = _text(last_user.get("content"))
        if body.get("model") == "model-that-does-not-exist":
            return h._json(400, {"error": {"message": f"The model does not exist. Request said: {user_text}", "type": "invalid_request_error"}})

        tools = body.get("tools") or []
        tool_results = [m for m in messages if m.get("role") == "tool"]
        message: dict
        if tools and not tool_results:
            fn = tools[0]["function"]
            props = fn.get("parameters", {}).get("properties", {})
            arg = next(iter(props), "value")
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_fake_0001",
                        "type": "function",
                        "function": {"name": fn["name"], "arguments": json.dumps({arg: self.tool_arg})},
                    }
                ],
            }
            finish = "tool_calls"
        else:
            text = f"Answer: {_text(tool_results[-1].get('content'))}" if tool_results else f"Answer: {user_text}"
            message = {"role": "assistant", "content": text}
            finish = "stop"

        usage = {"prompt_tokens": PROMPT_TOKENS, "completion_tokens": COMPLETION_TOKENS, "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS}
        base = {"id": "chatcmpl-fake", "created": int(time.time()), "model": body.get("model", "fake-model")}
        if not body.get("stream"):
            return h._json(200, {**base, "object": "chat.completion", "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage})

        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream")
        h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()

        def send(payload) -> None:
            data = (f"data: {payload}\n\n" if isinstance(payload, str) else f"data: {json.dumps(payload)}\n\n").encode()
            h.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")

        chunk = {**base, "object": "chat.completion.chunk"}
        send({**chunk, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
        if "tool_calls" in message:
            call = message["tool_calls"][0]
            send({**chunk, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": call["id"], "type": "function", "function": {"name": call["function"]["name"], "arguments": ""}}]}, "finish_reason": None}]})
            send({**chunk, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": call["function"]["arguments"]}}]}, "finish_reason": None}]})
        else:
            words = message["content"].split(" ")
            for i, word in enumerate(words):
                send({**chunk, "choices": [{"index": 0, "delta": {"content": word + (" " if i < len(words) - 1 else "")}, "finish_reason": None}]})
        send({**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
        if (body.get("stream_options") or {}).get("include_usage"):
            send({**chunk, "choices": [], "usage": usage})
        send("[DONE]")
        h.wfile.write(b"0\r\n\r\n")


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


if __name__ == "__main__":  # python tests/fake_openai.py --port 8999 --api-key KEY
    import argparse

    parser = argparse.ArgumentParser(description="OpenAI-compatible stand-in for run_e2e.sh. Not OpenAI.")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--api-key", default="stand-in-key")
    args = parser.parse_args()
    fake = FakeOpenAI(api_key=args.api_key, port=args.port)
    print("FAKE_OPENAI_URL", fake.url, flush=True)
    threading.Event().wait()
