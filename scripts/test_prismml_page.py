"""Execute the published PrismML guide against a loopback model and OTLP receiver."""

import gzip
import json
import os
from pathlib import Path
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.protobuf.json_format import MessageToDict
import openai
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
import pytest
from traceai_openai import OpenAIInstrumentor

PAGE = Path(__file__).resolve().parents[1] / "src/pages/docs/integrations/providers/prismml.mdx"


@pytest.mark.parametrize("mode", ["chat", "hidden", "error", "cancel"])
def test_exact_page_code(monkeypatch, capsys, mode):
    for name in list(os.environ):
        if name.startswith(("FI_", "OTEL_", "OPENAI_", "PRISMML_")) or name.lower() in (
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        ):
            monkeypatch.delenv(name)
    monkeypatch.setenv("NO_PROXY", "*")
    original_connect = socket.socket.connect

    def local_only(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            assert address[0] in ("127.0.0.1", "::1")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
    calls, exports = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            headers = {key.lower(): value for key, value in self.headers.items()}
            if self.path == "/tracer/v1/traces":
                if headers.get("content-encoding") == "gzip":
                    body = gzip.decompress(body)
                exports.append((headers, MessageToDict(ExportTraceServiceRequest.FromString(body))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"")
                return
            calls.append((self.path, headers, json.loads(body)))
            if mode == "error":
                payload = {"error": {"message": "Synthetic rejected role", "type": "invalid_request_error"}}
            else:
                payload = {
                    "id": "synthetic-bonsai", "object": "chat.completion", "created": 1,
                    "model": "bonsai-loaded",
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {
                        "role": "assistant", "content": "Paris is the capital of France.",
                    }}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17},
                }
            self.send_response(400 if mode == "error" else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("PRISMML_BASE_URL", origin + "/v1")
    monkeypatch.setenv("FI_BASE_URL", origin)
    monkeypatch.setenv("FI_API_KEY", "synthetic-fi-key")
    monkeypatch.setenv("FI_SECRET_KEY", "synthetic-fi-secret")
    for name in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        monkeypatch.setenv(name, str(mode == "hidden").lower())
    code = re.search(r"```python\n(.*?)```", PAGE.read_text(), re.S).group(1)
    namespace = {}
    interruption = KeyboardInterrupt("synthetic guide cancellation")
    if mode == "cancel":
        # Interrupt the SDK's default HTTP client, not the instrumented method.
        # This supports both httpx (floor) and httpx2 (latest SDK).
        # The guide's finally/force_flush must export one ended ERROR span.
        def interrupted_send(self, request, **kwargs):
            calls.append((request.url.path, dict(request.headers), json.loads(request.content)))
            raise interruption

        monkeypatch.setattr(openai.DefaultHttpxClient, "send", interrupted_send)
    try:
        if mode == "cancel":
            with pytest.raises(KeyboardInterrupt) as caught:
                exec(compile(code, str(PAGE), "exec"), namespace)
            assert caught.value is interruption
        elif mode == "error":
            with pytest.raises(openai.BadRequestError):
                exec(compile(code, str(PAGE), "exec"), namespace)
        else:
            exec(compile(code, str(PAGE), "exec"), namespace)
            assert capsys.readouterr().out.strip() == "Paris is the capital of France."
        assert len(calls) == len(exports) == 1
        path, headers, body = calls[0]
        assert path == "/v1/chat/completions"
        assert headers["authorization"] == "Bearer not-needed"
        assert "x-api-key" not in headers and "x-secret-key" not in headers
        assert "synthetic-fi-" not in json.dumps(calls)
        assert body["model"] == "bonsai"
        export_headers, payload = exports[0]
        assert export_headers["x-api-key"] == "synthetic-fi-key"
        assert export_headers["x-secret-key"] == "synthetic-fi-secret"
        resource = payload["resourceSpans"][0]
        def attrs(items):
            return {item["key"]: next(iter(item["value"].values())) for item in items}

        assert attrs(resource["resource"]["attributes"])["project_name"] == "prismml-bonsai"
        assert attrs(resource["resource"]["attributes"])["project_type"] == "observe"
        spans = [span for rs in payload["resourceSpans"] for scope in rs["scopeSpans"] for span in scope["spans"]]
        assert len(spans) == 1
        span = spans[0]
        assert span["name"] == "ChatCompletion"
        attributes = attrs(span["attributes"])
        assert attributes["gen_ai.span.kind"] == "LLM"
        assert attributes["gen_ai.provider.name"] == "openai"
        assert attributes["gen_ai.request.model"] == ("bonsai" if mode in ("error", "cancel") else "bonsai-loaded")
        assert "not-needed" not in json.dumps(payload)
        if mode in ("error", "cancel"):
            assert span["status"]["code"] == "STATUS_CODE_ERROR"
            assert any(event["name"] == "exception" for event in span["events"])
        else:
            assert int(attributes["gen_ai.usage.total_tokens"]) == 17
            assert attributes["output.value"] == ("__REDACTED__" if mode == "hidden" else "Paris is the capital of France.")
        if mode == "hidden":
            assert "capital of France" not in json.dumps(payload)
            assert "gen_ai.request.parameters" not in attributes
    finally:
        OpenAIInstrumentor().uninstrument()
        if "provider" in namespace:
            namespace["provider"].shutdown()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
