"""Run the exact page snippet through real registration and a loopback OTLP receiver.

Only the gateway transport is fake. No vendor or Future AGI service is contacted.
"""
import gzip
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import openai
import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from traceai_openai import OpenAIInstrumentor

from test_client_tracing import httpx

PAGE = Path(__file__).resolve().parents[4] / "src/pages/docs/integrations/gateways/truefoundry.mdx"
PRIVACY_FLAGS = (
    "FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_INPUT_MESSAGES",
    "FI_HIDE_OUTPUT_MESSAGES", "FI_HIDE_LLM_INVOCATION_PARAMETERS", "FI_HIDE_ERROR_DETAILS",
)


@pytest.fixture()
def receiver():
    received = []

    class Sink(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append((self.path, dict(self.headers), self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def decode_request(received):
    path, headers, raw = received
    headers = {k.lower(): v for k, v in headers.items()}
    body = gzip.decompress(raw) if headers.get("content-encoding") == "gzip" else raw
    request = ExportTraceServiceRequest.FromString(body)
    return path, headers, body, request


def attributes(values):
    return {v.key: getattr(v.value, v.value.WhichOneof("value")) for v in values}


@pytest.mark.parametrize("compression", ["none", "gzip"])
@pytest.mark.parametrize("private", [False, True])
def test_page_client_snippet_runs(monkeypatch, capsys, receiver, compression, private):
    page = PAGE.read_text()
    snippet = next(b for b in re.findall(r"```python\n(.*?)\n```", page, re.S) if "register(" in b)
    endpoint, received = receiver
    monkeypatch.setenv("FI_BASE_URL", endpoint)
    monkeypatch.setenv("FI_API_KEY", "synthetic-fi-key")
    monkeypatch.setenv("FI_SECRET_KEY", "synthetic-fi-secret")
    monkeypatch.setenv("TFY_API_KEY", "synthetic-tfy-token")
    monkeypatch.setenv("TFY_MODEL", "openai-main/gpt-4o-mini")
    monkeypatch.setenv("TFY_BASE_URL", "https://gateway.truefoundry.ai")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_COMPRESSION", compression)
    for flag in PRIVACY_FLAGS:
        assert flag in page
        monkeypatch.setenv(flag, str(private).lower())

    def gateway(request):
        assert request.url == "https://gateway.truefoundry.ai/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-tfy-token"
        assert "x-api-key" not in request.headers and "x-secret-key" not in request.headers
        assert json.loads(request.content)["model"] == "openai-main/gpt-4o-mini"
        return httpx.Response(200, json={
            "id": "c1", "object": "chat.completion", "created": 1, "model": "gpt-4o-mini-2024-07-18",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Paris"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 14, "completion_tokens": 1, "total_tokens": 15},
        })

    class MockedOpenAI(openai.OpenAI):
        def __init__(self, **kwargs):
            super().__init__(http_client=httpx.Client(transport=httpx.MockTransport(gateway)), **kwargs)

    monkeypatch.setattr(openai, "OpenAI", MockedOpenAI)
    try:
        exec(compile(snippet, str(PAGE), "exec"), {"__name__": "page_snippet"})
    finally:
        OpenAIInstrumentor().uninstrument()

    assert capsys.readouterr().out.strip() == "Paris"
    assert len(received) == 1
    path, headers, body, request = decode_request(received[0])
    assert path == "/tracer/v1/traces"
    assert headers["content-type"] == "application/x-protobuf"
    assert headers.get("content-encoding", "none") == compression
    assert headers["x-api-key"] == "synthetic-fi-key"
    assert headers["x-secret-key"] == "synthetic-fi-secret"
    for credential in (b"synthetic-fi-key", b"synthetic-fi-secret", b"synthetic-tfy-token"):
        assert credential not in body
    (resource,) = request.resource_spans
    assert attributes(resource.resource.attributes)["project_name"] == "my-chatbot"
    assert attributes(resource.resource.attributes)["project_type"] == "observe"
    (scope,) = resource.scope_spans
    (span,) = scope.spans
    assert span.name == "ChatCompletion"
    assert attributes(span.attributes)["gen_ai.usage.total_tokens"] == 15
    assert (b"capital of France" in body) is not private
    assert (b"Paris" in body) is not private


def test_page_pins_match_installable_example():
    requirements = (PAGE.parents[5] / "examples/gateways/truefoundry/requirements.txt").read_text()
    page = PAGE.read_text()
    for name in ("traceai-openai", "fi-instrumentation-otel", "openai"):
        pin = re.search(rf"^{name}==[^\s]+", requirements, re.M).group()
        assert f'"{pin}"' in page
