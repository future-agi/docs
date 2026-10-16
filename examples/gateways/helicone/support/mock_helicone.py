"""STANDIN for Helicone's hosted endpoints: a small OpenAI-compatible server.

It is NOT Helicone. It speaks the OpenAI chat-completions wire format on two
path prefixes that mirror the two Helicone surfaces, and it enforces the auth
shape each surface documents, so a recipe that mixes the two fails here too:

  /gw            AI Gateway shape  - Authorization: Bearer <HELICONE key>
                 (base URL for the client: http://127.0.0.1:PORT/gw)
  /proxy/v1      classic proxy     - Authorization: Bearer <provider key>
                 AND Helicone-Auth: Bearer <HELICONE key>
                 (base URL for the client: http://127.0.0.1:PORT/proxy/v1)

Behaviour:
  * a request with `tools` and no tool result yet returns a `get_weather` tool call;
    with a tool result it returns a final answer
  * `stream: true` returns SSE chunks (a final usage chunk with
    `stream_options.include_usage`)
  * model `force-500` returns HTTP 500 with a body that contains a marker string
  * every request is recorded in `server.requests` (path, lower-cased headers, JSON body)
"""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USAGE_TOOL_TURN = {"prompt_tokens": 31, "completion_tokens": 17, "total_tokens": 48}
USAGE_FINAL_TURN = {"prompt_tokens": 63, "completion_tokens": 9, "total_tokens": 72}
ERROR_BODY_MARKER = "UPSTREAM-ERROR-BODY-MARKER"
_MARK = re.compile(r"HELI-MARK-[A-Za-z0-9]+")


def _find_marker(messages):
    """The tests put a unique HELI-MARK-... token in the prompt; the mock echoes it back."""
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            hit = _MARK.search(content)
            if hit:
                return hit.group(0)
    return ""


def _bearer(value):
    if value and value.lower().startswith("bearer "):
        return value[7:].strip()
    return None


class MockHelicone:
    def __init__(self, helicone_key: str, host: str = "127.0.0.1", port: int = 0):
        self.helicone_key = helicone_key
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        mock = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send_json(self, code, obj, extra=None):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                hdrs = {k.lower(): v for k, v in self.headers.items()}
                try:
                    body = json.loads(raw or b"{}")
                except ValueError:
                    body = {}
                with mock._lock:
                    mock.requests.append({"path": self.path, "headers": hdrs, "body": body})

                path = self.path.split("?")[0]
                if path.startswith("/gw") and path.endswith("/chat/completions"):
                    if _bearer(hdrs.get("authorization")) != mock.helicone_key:
                        return self._send_json(
                            401, {"error": {"message": "mock: invalid Helicone API key", "type": "invalid_request_error"}}
                        )
                elif path.startswith("/proxy/v1") and path.endswith("/chat/completions"):
                    if _bearer(hdrs.get("helicone-auth")) != mock.helicone_key:
                        return self._send_json(
                            401, {"error": {"message": "mock: missing or invalid Helicone-Auth", "type": "invalid_request_error"}}
                        )
                    if not _bearer(hdrs.get("authorization")):
                        return self._send_json(
                            401, {"error": {"message": "mock: missing provider key", "type": "invalid_request_error"}}
                        )
                else:
                    return self._send_json(404, {"error": {"message": f"mock: no route {path}"}})

                model = body.get("model", "mock-model")
                if model == "force-500":
                    return self._send_json(
                        500, {"error": {"message": f"mock provider failure {ERROR_BODY_MARKER}", "type": "server_error"}}
                    )
                response_model = model.split("/", 1)[-1]  # the gateway reports the resolved model, no provider prefix
                msgs = body.get("messages", [])
                has_tool_result = any(m.get("role") == "tool" for m in msgs)
                wants_tool = bool(body.get("tools")) and not has_tool_result
                usage = USAGE_TOOL_TURN if wants_tool else USAGE_FINAL_TURN
                marker = _find_marker(msgs)
                if wants_tool:
                    message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_mock_1",
                                "type": "function",
                                "function": {"name": "get_weather", "arguments": json.dumps({"city": f"Paris {marker}".strip()})},
                            }
                        ],
                    }
                    finish = "tool_calls"
                else:
                    message = {"role": "assistant", "content": f"It is 21C and sunny in Paris. {marker}".strip()}
                    finish = "stop"
                extra = {"helicone-id": "mock-helicone-request-id"}
                if body.get("stream"):
                    return self._stream(response_model, message, finish, usage, body, extra)
                self._send_json(
                    200,
                    {
                        "id": "chatcmpl-mock-1",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": response_model,
                        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                        "usage": usage,
                    },
                    extra,
                )

            def _stream(self, model, message, finish, usage, body, extra):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                for k, v in extra.items():
                    self.send_header(k, v)
                self.end_headers()

                def chunk(obj):
                    payload = ("data: " + json.dumps(obj) + "\n\n").encode()
                    self.wfile.write(f"{len(payload):x}\r\n".encode() + payload + b"\r\n")

                base = {"id": "chatcmpl-mock-1", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
                chunk({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
                text = message.get("content") or ""
                for word in text.split(" ") if text else []:
                    chunk({**base, "choices": [{"index": 0, "delta": {"content": word + " "}, "finish_reason": None}]})
                chunk({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
                if (body.get("stream_options") or {}).get("include_usage"):
                    chunk({**base, "choices": [], "usage": usage})
                done = b"data: [DONE]\n\n"
                self.wfile.write(f"{len(done):x}\r\n".encode() + done + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")

        self._server = ThreadingHTTPServer((host, port), Handler)
        self.port = self._server.server_address[1]
        self.base = f"http://{host}:{self.port}"
        self.gateway_base_url = f"{self.base}/gw"
        self.proxy_base_url = f"{self.base}/proxy/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


if __name__ == "__main__":  # python -m support.mock_helicone --port 18303
    import argparse
    import os

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18303)
    ap.add_argument("--key", default=os.environ.get("MOCK_HELICONE_KEY", "sk-helicone-mock-key"))
    a = ap.parse_args()
    with MockHelicone(a.key, port=a.port) as m:
        print(f"mock helicone on {m.base}  (gateway {m.gateway_base_url}, proxy {m.proxy_base_url})", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
