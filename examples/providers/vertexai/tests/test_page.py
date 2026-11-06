"""Run the published page with the real SDK and a loopback OTLP receiver.

Install pytest, traceAI-google-genai==0.1.3, fi-instrumentation-otel==1.2.2,
and either google-genai==1.8.0 (floor) or google-genai==2.34.0 (current).
Run with non-local outbound networking denied. No Google/Future AGI API calls.
"""

import json
import os
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import google.auth
from google.auth.credentials import AnonymousCredentials
import httpx
import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

import fi_instrumentation
from fi_instrumentation.fi_types import SpanAttributes
from traceai_google_genai import GoogleGenAIInstrumentor


PAGE = Path(os.environ.get(
    "VERTEXAI_PAGE_PATH",
    Path(__file__).resolve().parents[4]
    / "src/pages/docs/integrations/traceai/vertexai.mdx",
))
PROMPT = "Write a haiku about a mountain trail."
ANSWER = "Pine shadows whisper / Footsteps climb the mountain trail / Clouds settle softly."


def page_code():
    page = PAGE.read_text()
    assert "from traceai_google_genai import GoogleGenAIInstrumentor" in page, (
        "The recommended route must use maintained Google Gen AI instrumentation"
    )
    blocks = re.findall(r"```python\n(.*?)```", page, re.DOTALL)
    assert len(blocks) == 1, "Use one complete recommended application example"
    assert "vertexai=True" in blocks[0]
    return compile(blocks[0], str(PAGE), "exec")


def attributes(values):
    return {item.key: getattr(item.value, item.value.WhichOneof("value")) for item in values}


@pytest.mark.parametrize("location,hide_content", [
    ("global", False), ("us-central1", False), ("global", True),
])
def test_page_generation_exports_one_span(monkeypatch, capsys, location, hide_content):
    code = page_code()
    wire = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            wire.append((self.path, self.headers, ExportTraceServiceRequest.FromString(body)))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for key, value in {
        "FI_API_KEY": "synthetic-fi-key",
        "FI_SECRET_KEY": "synthetic-fi-secret",
        "FI_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "FI_HIDE_INPUTS": str(hide_content).lower(),
        "FI_HIDE_OUTPUTS": str(hide_content).lower(),
        "GOOGLE_CLOUD_PROJECT": "synthetic-project",
        "GOOGLE_CLOUD_LOCATION": location,
        "GOOGLE_GENAI_MODEL": "synthetic-model",
    }.items():
        monkeypatch.setenv(key, value)
    # Never discover or refresh real Application Default Credentials.
    credentials = AnonymousCredentials()
    credentials.token = "synthetic-google-token"
    monkeypatch.setattr(google.auth, "default", lambda **kwargs: (
        credentials, "synthetic-project",
    ))
    requests = []

    def send(client, request, **kwargs):
        # The SDK still builds/serializes a real Vertex request. Only transport is synthetic.
        host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
        assert request.url.host == host
        assert request.headers["Authorization"] == "Bearer synthetic-google-token"
        assert f"/projects/synthetic-project/locations/{location}/" in request.url.path
        assert request.url.path.endswith("/publishers/google/models/synthetic-model:generateContent")
        payload = json.loads(request.content)
        assert payload["contents"][0]["parts"][0]["text"] == PROMPT
        requests.append(request)
        return httpx.Response(200, request=request, json={
            "candidates": [{"index": 0, "content": {
                "role": "model", "parts": [{"text": ANSWER}],
            }, "finishReason": "STOP"}],
            "modelVersion": "synthetic-model",
            "usageMetadata": {
                "promptTokenCount": 12, "candidatesTokenCount": 8, "totalTokenCount": 20,
            },
        })

    monkeypatch.setattr(httpx.Client, "send", send)
    providers = []
    original_register = fi_instrumentation.register

    def register(**kwargs):
        provider = original_register(**kwargs)
        providers.append(provider)
        return provider

    monkeypatch.setattr(fi_instrumentation, "register", register)
    try:
        exec(code, {"__name__": "__main__"})
        assert ANSWER in capsys.readouterr().out
        assert len(requests) == 1
        assert len(wire) == 1, "The page must flush one export without duplicate instrumentation"
        path, headers, export = wire[0]
        assert path == "/tracer/v1/traces"
        assert headers["Content-Type"] == "application/x-protobuf"
        assert headers["X-Api-Key"] == "synthetic-fi-key"
        assert headers["X-Secret-Key"] == "synthetic-fi-secret"
        resource_spans, = export.resource_spans
        resource = attributes(resource_spans.resource.attributes)
        assert resource["project_name"] == "vertexai_app"
        assert resource["project_type"] == "observe"
        spans = [span for scope in resource_spans.scope_spans for span in scope.spans]
        span, = spans
        attrs = attributes(span.attributes)
        assert span.name == "GenerateContent"
        assert span.status.code == 1  # OTLP STATUS_CODE_OK
        assert len(span.trace_id) == 16 and len(span.span_id) == 8
        assert attrs[SpanAttributes.GEN_AI_SPAN_KIND] == "LLM"
        assert attrs[SpanAttributes.GEN_AI_REQUEST_MODEL] == "synthetic-model"
        assert attrs[SpanAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
        assert attrs[SpanAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 8
        assert attrs[SpanAttributes.GEN_AI_USAGE_TOTAL_TOKENS] == 20
        serialized = export.SerializeToString()
        assert b"synthetic-fi-key" not in serialized
        assert b"synthetic-fi-secret" not in serialized
        assert b"synthetic-google-token" not in serialized
        if hide_content:
            assert PROMPT.encode() not in serialized
            assert ANSWER.encode() not in serialized
        else:
            assert PROMPT in attrs[SpanAttributes.INPUT_VALUE]
            assert ANSWER in attrs[SpanAttributes.OUTPUT_VALUE]
    finally:
        GoogleGenAIInstrumentor().uninstrument()
        for provider in providers:
            provider.shutdown()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
