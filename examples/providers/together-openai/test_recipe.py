"""Exercise the published Together/OpenAI recipe without vendor credentials or calls."""

import asyncio
import gzip
import json
import os
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import openai
import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from traceai_openai import OpenAIInstrumentor

# Use the module imported by the SDK itself, even if both HTTP packages exist.
try:
    from openai._base_client import httpx2 as httpx
except ImportError:
    from openai._base_client import httpx

PAGE = (
    Path(__file__).resolve().parents[3]
    / "src/pages/docs/integrations/traceai/togetherai.mdx"
)
MODEL = "openai/gpt-oss-120b"
MESSAGES = [{"role": "user", "content": "Name a place to visit in San Francisco."}]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("FI_", "OTEL_", "OPENAI_", "TOGETHER_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    connect = socket.socket.connect

    def local_only(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            assert address[0] in ("127.0.0.1", "::1"), (
                "Non-loopback network is forbidden"
            )
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)


def respond(request):
    assert request.url.host == "api.together.ai"
    assert request.headers["authorization"].startswith("Bearer ")
    assert "x-api-key" not in request.headers
    assert "x-secret-key" not in request.headers
    body = json.loads(request.content)
    if body["model"] == "synthetic-error":
        return httpx.Response(
            400,
            request=request,
            json={
                "error": {
                    "message": "Synthetic failure",
                    "type": "invalid_request_error",
                }
            },
        )
    if request.url.path.endswith("/embeddings"):
        payload = {
            "object": "list",
            "model": MODEL,
            "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 2, "total_tokens": 2},
        }
        return httpx.Response(200, request=request, json=payload)
    chat = "/chat/" in request.url.path
    choice = {"index": 0, "finish_reason": "stop"}
    if chat:
        choice["delta" if body.get("stream") else "message"] = {
            "role": "assistant",
            "content": "Visit Golden Gate Park.",
        }
    else:
        choice["text"] = "Visit Golden Gate Park."
    payload = {
        "id": "synthetic",
        "object": "chat.completion.chunk" if body.get("stream") else "chat.completion",
        "created": 1,
        "model": MODEL,
        "choices": [choice],
        "usage": {"prompt_tokens": 2, "completion_tokens": 4, "total_tokens": 6},
    }
    if body.get("stream"):
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/event-stream"},
            text="data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n",
        )
    return httpx.Response(200, request=request, json=payload)


@pytest.fixture
def traced():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        yield exporter
    finally:
        instrumentor.uninstrument()
        provider.shutdown()


def call(client, surface):
    if surface == "embeddings":
        return client.embeddings.create(model=MODEL, input="A place to visit")
    if surface == "completions":
        return client.completions.create(model=MODEL, prompt="A place to visit")
    return client.chat.completions.create(
        model="synthetic-error" if surface == "error" else MODEL,
        messages=MESSAGES,
        **({"stream": True} if surface == "stream" else {}),
    )


@pytest.mark.parametrize(
    "surface", ["chat", "completions", "embeddings", "stream", "error"]
)
@pytest.mark.parametrize("asynchronous", [False, True])
def test_together_attribution(traced, surface, asynchronous):
    kwargs = {
        "api_key": "synthetic-together-key",
        "base_url": "https://api.together.ai/v1",
        "max_retries": 0,
    }

    async def run_async():
        async with openai.AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ) as client:
            if surface == "error":
                with pytest.raises(openai.BadRequestError):
                    await call(client, surface)
            else:
                response = await call(client, surface)
                if surface == "stream":
                    assert [
                        chunk.choices[0].delta.content async for chunk in response
                    ] == ["Visit Golden Gate Park."]

    if asynchronous:
        asyncio.run(run_async())
    else:
        with openai.OpenAI(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))
        ) as client:
            if surface == "error":
                with pytest.raises(openai.BadRequestError):
                    call(client, surface)
            else:
                response = call(client, surface)
                if surface == "stream":
                    assert [chunk.choices[0].delta.content for chunk in response] == [
                        "Visit Golden Gate Park."
                    ]
    (span,) = traced.get_finished_spans()
    assert span.attributes["gen_ai.provider.name"] == "together"
    assert (span.status.status_code.name == "ERROR") == (surface == "error")


def test_page_matches_released_provider_behavior(traced):
    with openai.OpenAI(
        api_key="synthetic-together-key",
        base_url="https://api.together.ai/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as client:
        call(client, "chat")
    (span,) = traced.get_finished_spans()
    assert span.attributes["gen_ai.provider.name"] == "together"
    page = PAGE.read_text()
    assert "can be labeled **OpenAI**" not in page, (
        "The guide contradicts the released instrumentor"
    )
    assert '"traceAI-openai>=0.1.11"' in page
    assert '"fi-instrumentation-otel>=1.2.2"' in page
    assert "gen_ai.provider.name=together" in page


@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_exact_page_snippets_export_to_loopback(monkeypatch, compression):
    exports = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers["content-length"]))
            if self.headers.get("content-encoding") == "gzip":
                raw = gzip.decompress(raw)
            message = ExportTraceServiceRequest.FromString(raw)
            exports.append((self.path, dict(self.headers), message))
            self.send_response(200)
            self.send_header("content-type", "application/x-protobuf")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("FI_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_COMPRESSION", compression)
    monkeypatch.setattr(
        httpx.Client, "send", lambda self, request, **kwargs: respond(request)
    )
    code = "\n".join(re.findall(r"```python\n(.*?)```", PAGE.read_text(), re.DOTALL))
    namespace = {}
    try:
        # Execute the version-controlled guide under loopback-only networking.
        exec(compile(code, str(PAGE), "exec"), namespace)  # noqa: S102
    finally:
        if "client" in namespace:
            namespace["client"].close()
        if "trace_provider" in namespace:
            namespace["trace_provider"].shutdown()
        OpenAIInstrumentor().uninstrument()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert len(exports) == 1
    path, headers, message = exports[0]
    headers = {key.lower(): value for key, value in headers.items()}
    assert path == "/tracer/v1/traces"
    assert headers["content-type"] == "application/x-protobuf"
    assert headers.get("content-encoding") == (
        "gzip" if compression == "gzip" else None
    )
    assert headers["x-api-key"] == "your-futureagi-api-key"
    assert headers["x-secret-key"] == "your-futureagi-secret-key"
    (resource_spans,) = message.resource_spans
    resource = {
        item.key: item.value.string_value for item in resource_spans.resource.attributes
    }
    assert resource["project_name"] == "togetherai_project"
    spans = [span for scope in resource_spans.scope_spans for span in scope.spans]
    (span,) = spans
    attrs = {item.key: item.value.string_value for item in span.attributes}
    assert attrs["gen_ai.provider.name"] == "together"
    assert attrs["gen_ai.request.model"] == MODEL
    for credential in (
        "your-together-api-key",
        "your-futureagi-api-key",
        "your-futureagi-secret-key",
    ):
        assert credential not in str(message)
