"""A deterministic stand-in for an OpenAI-compatible /v1/chat/completions endpoint.

It exists only so the unit tests run offline, without a key. It is NOT a model and the
end-to-end script does not use it unless you leave OPENAI_API_KEY unset. Behaviour:

* a request whose model id contains "no-such-model" gets a 404 ``model_not_found`` error;
* a request that offers tools and has no tool result yet gets a ``get_weather`` tool call
  whose argument is the city named in the prompt (the last word before "?" or "." );
* otherwise it answers with a fixed sentence that repeats the last user message;
* ``stream: true`` is answered as server-sent events;
* usage is reported unless the server was started with ``usage=False``.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return str(content)
    return ""


def _city(text: str) -> str:
    match = re.search(r"weather in ([^?.,\s]+)", text)
    return match.group(1) if match else "Nowhere"


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-openai/1"

    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        self.server.requests.append({"path": self.path, "authorization": self.headers.get("authorization"), "body": request})
        if not self.path.endswith("/chat/completions"):
            return self._send(404, {"error": {"message": f"no route {self.path}", "type": "invalid_request_error"}})
        model = request.get("model", "")
        if "no-such-model" in model:
            return self._send(
                404,
                {"error": {"message": f"The model `{model}` does not exist", "type": "invalid_request_error", "code": "model_not_found"}},
            )
        messages = request.get("messages", [])
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        message: dict
        finish = "stop"
        if request.get("tools") and not has_tool_result:
            city = _city(_last_user_text(messages))
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_fake_1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": json.dumps({"city": city})},
                    }
                ],
            }
            finish = "tool_calls"
        elif has_tool_result:
            tool_text = next(m["content"] for m in reversed(messages) if m.get("role") == "tool")
            message = {"role": "assistant", "content": f"The weather report says: {tool_text}"}
        else:
            message = {"role": "assistant", "content": f"Fake answer to: {_last_user_text(messages)}"}
        usage = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18} if self.server.usage else None

        if request.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            text = message.get("content") or ""
            pieces = [text[i : i + 12] for i in range(0, len(text), 12)] or [""]
            for piece in pieces:
                chunk = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": model,
                         "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            last = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
            if usage and (request.get("stream_options") or {}).get("include_usage"):
                last["usage"] = usage
            self.wfile.write(f"data: {json.dumps(last)}\n\ndata: [DONE]\n\n".encode())
            return
        body = {"id": "chatcmpl-fake", "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "message": message, "finish_reason": finish}]}
        if usage:
            body["usage"] = usage
        self._send(200, body)


class FakeOpenAI(ThreadingHTTPServer):
    def __init__(self, port: int = 0, usage: bool = True) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.usage = usage
        self.requests: list[dict] = []
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1"

    def start(self) -> "FakeOpenAI":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-usage", action="store_true")
    args = parser.parse_args()
    server = FakeOpenAI(args.port, usage=not args.no_usage).start()
    print(server.base_url, flush=True)
    threading.Event().wait()
