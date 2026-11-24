"""Exercise the published Together/OpenAI recipe without vendor credentials or calls."""

import asyncio
import gzip
import json
import os
import re
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
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


def respond(request, *, response_model=MODEL, answer="Visit Golden Gate Park."):
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
            "content": answer,
        }
    else:
        choice["text"] = answer
    payload = {
        "id": "synthetic",
        "object": "chat.completion.chunk" if body.get("stream") else "chat.completion",
        "created": 1,
        "model": response_model,
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
    for package in ("traceAI-openai", "fi-instrumentation-otel", "httpx"):
        assert f"{package}=={version(package)}" in page
    assert "gen_ai.provider.name=together" in page


@pytest.fixture(scope="module")
def page_examples():
    blocks = re.findall(
        r"^```([^\n]*)\n(.*?)^```$", PAGE.read_text(), re.MULTILINE | re.DOTALL
    )
    assert [lang for lang, _ in blocks] == ["bash", "sh", "python", "python"]
    _, (_, setup), (_, returns), (_, routing) = blocks
    # Run the exports in an empty environment: only the documented placeholders
    # should reach the examples, never credentials from the runner.
    expected = {
        "FI_TRACES_URL": "https://api.futureagi.com",
        "TOGETHER_API_KEY": "YOUR_PROVIDER_KEY",
        "TOGETHER_MODEL": MODEL,
        "FI_API_KEY": "YOUR_FUTURE_AGI_API_KEY",
        "FI_SECRET_KEY": "YOUR_FUTURE_AGI_SECRET_KEY",
    }
    # Compare the full environment delta: do not silently drop an extra export
    # that would change the SDK's behavior when a reader runs the next block.
    def shell_env(commands):
        output = subprocess.check_output(["sh", "-ec", commands + "\nenv"], env={}, text=True)
        return dict(line.split("=", 1) for line in output.splitlines())

    baseline = shell_env("")
    exported = shell_env(setup)
    assert exported == baseline | expected
    return expected, {"returns.py": returns, "check_routing.py": routing}


@pytest.mark.parametrize("compression", ["none", "gzip"])
@pytest.mark.parametrize("script", ["returns.py", "check_routing.py"])
def test_exact_page_snippets_export_to_loopback(
    monkeypatch, capsys, page_examples, compression, script
):
    env, examples = page_examples
    routing = script == "check_routing.py"
    requested_model = MODEL if routing else "synthetic-account-model"
    exports = []
    requests = []
    answer = "Yes, an unused pack is eligible on day 12."
    served_model = "synthetic-served-model"

    provider_key = "unused" if routing else env["TOGETHER_API_KEY"]
    send = httpx.Client.send

    def observe_request(self, request, **kwargs):
        assert str(request.url) == "https://api.together.ai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + provider_key
        assert "x-api-key" not in request.headers and "x-secret-key" not in request.headers
        requests.append(json.loads(request.content))
        return send(self, request, **kwargs)

    def provider_transport(self, request):
        # The routing example must use its own failing MockTransport, not this stub.
        if routing:
            pytest.fail("The routing check tried to contact the provider")
        return respond(request, response_model=served_model, answer=answer)

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
    for key, value in env.items():
        if not (routing and key.startswith("TOGETHER_")):
            monkeypatch.setenv(key, value)
    if not routing:
        monkeypatch.setenv("TOGETHER_MODEL", requested_model)
    # Distinct origins prove FI_TRACES_URL, not FI_BASE_URL, routes the export.
    monkeypatch.setenv("FI_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("FI_TRACES_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_COMPRESSION", compression)
    monkeypatch.setattr(httpx.Client, "send", observe_request)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", provider_transport)
    try:
        exec(compile(examples[script], script, "exec"), {  # noqa: S102
            "__name__": "__main__", "__file__": script,
        })
    finally:
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
    assert headers["x-api-key"] == env["FI_API_KEY"]
    assert headers["x-secret-key"] == env["FI_SECRET_KEY"]
    (resource_spans,) = message.resource_spans
    resource = {
        item.key: item.value.string_value for item in resource_spans.resource.attributes
    }
    assert resource["project_name"] == (
        "ridgeline-returns-routing-check" if routing else "ridgeline-returns"
    )
    (span,) = [span for scope in resource_spans.scope_spans for span in scope.spans]
    assert span.name == "ChatCompletion"
    attrs = {item.key: item.value for item in span.attributes}
    assert attrs["gen_ai.provider.name"].string_value == "together"
    assert json.loads(attrs["gen_ai.request.parameters"].string_value)["model"] == requested_model
    assert attrs["gen_ai.request.model"].string_value == (
        MODEL if routing else served_model
    )
    stdout = capsys.readouterr().out.splitlines()
    (body,) = requests
    assert body["model"] == requested_model
    if routing:
        assert body["messages"] == [{"role": "user", "content": "Routing check"}]
        assert span.status.code == span.status.STATUS_CODE_ERROR
        assert "Local connection error; check the failed span in Observe." in stdout
        assert not any(key.startswith("gen_ai.usage.") for key in attrs)
    else:
        assert span.status.code != span.status.STATUS_CODE_ERROR
        assert body["messages"] == [{
            "role": "user",
            "content": "We accept unused packs within 30 days. Can I return an unused pack on day 12?",
        }]
        assert answer in stdout
        assert attrs["gen_ai.usage.input_tokens"].int_value == 2
        assert attrs["gen_ai.usage.output_tokens"].int_value == 4
        assert attrs["gen_ai.usage.total_tokens"].int_value == 6
    for credential in (provider_key, env["FI_API_KEY"], env["FI_SECRET_KEY"]):
        assert credential not in str(message)
