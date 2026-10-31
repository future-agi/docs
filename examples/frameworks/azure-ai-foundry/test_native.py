"""Execute the guide's Python block against released SDKs and a loopback OTLP sink.

Run with outbound network denied except localhost. No Azure/Future AGI service is
called. Both SDK transports and Azure credentials are synthetic. Each scenario
runs in a fresh process because OpenTelemetry's global provider is write-once.

Dependencies: the guide's install command, pytest, and traceAI-openai==0.1.11
(the last package is used only for the duplicate-instrumentation control).
Set OTELCOL_BINARY to the absolute path of otelcol-contrib 0.162.0; the test
executes the YAML and Python blocks directly from the guide.
"""
from __future__ import annotations

import contextlib
import gzip
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

PAGE = Path(__file__).resolve().parents[3] / "src/pages/docs/integrations/frameworks/azure-ai-foundry.mdx"


@pytest.mark.parametrize("mode", ["native", "content", "missing", "duplicate", "error"])
def test_guide(mode):
    result = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).resolve()), mode],
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1",
             "OTELCOL_BINARY": os.environ["OTELCOL_BINARY"]},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def probe(mode: str) -> dict:
    # Block non-loopback sockets as a second guard, even without OS sandboxing.
    connect = socket.socket.connect

    def local_connect(sock, address):
        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "::1"):
            raise AssertionError("Non-loopback connection forbidden")
        return connect(sock, address)

    socket.socket.connect = local_connect
    collector_binary = os.environ["OTELCOL_BINARY"]
    os.environ.clear()
    os.environ.update({
        "FI_API_KEY": "synthetic-fi-key",
        "FI_SECRET_KEY": "synthetic-fi-secret",
        "FI_PROJECT_NAME": "foundry-offline",
        "FOUNDRY_PROJECT_ENDPOINT": "https://fixture.services.ai.azure.com/api/projects/offline",
        "FOUNDRY_MODEL_NAME": "deployment",
        "AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING": "true",
        "AZURE_SDK_TRACING_IMPLEMENTATION": "opentelemetry",
        # The explicit False in the guide must override a stale content-on env.
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
        "NO_PROXY": "127.0.0.1,localhost",
    })

    from azure.ai.projects import AIProjectClient
    from azure.core.credentials import AccessToken
    from azure.core.pipeline.transport import HttpResponse, HttpTransport
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    from google.protobuf.json_format import MessageToDict
    import openai

    if importlib.metadata.version("openai").startswith("3."):
        import httpx2 as httpx
    else:
        import httpx

    requests = []
    batches = []

    class Sink(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path, dict(self.headers)))
            data = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            batch = ExportTraceServiceRequest.FromString(data)
            batches.append(batch)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["FI_TRACE_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/tracer/v1/traces"
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        collector_port = port_socket.getsockname()[1]
    os.environ["FI_BASE_URL"] = f"http://127.0.0.1:{collector_port}"
    configs = re.findall(r"```yaml\n(.*?)```", PAGE.read_text(), re.S)
    assert len(configs) == 1
    config_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml")
    config_file.write(configs[0].replace("127.0.0.1:4318", f"127.0.0.1:{collector_port}"))
    config_file.flush()
    collector = subprocess.Popen(
        [collector_binary, "--config", config_file.name],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.monotonic() + 15
    while True:
        if collector.poll() is not None:
            raise AssertionError(collector.communicate()[0])
        try:
            with socket.create_connection(("127.0.0.1", collector_port), timeout=0.2):
                break
        except OSError:
            if time.monotonic() > deadline:
                collector.terminate()
                raise AssertionError(collector.communicate(timeout=10)[0])
            time.sleep(0.05)

    class Credential:
        def get_token(self, *_args, **_kwargs):
            return AccessToken("synthetic-azure-token", 4102444800)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    class Response(HttpResponse):
        def __init__(self, request, status, payload):
            super().__init__(request, None)
            self.status_code = status
            self.headers = {"Content-Type": "application/json"}
            self.content_type = "application/json"
            self.reason = "OK"
            self.payload = json.dumps(payload).encode()

        def body(self):
            return self.payload

        def json(self):
            return json.loads(self.payload)

    operations = []

    class Transport(HttpTransport):
        def open(self):
            pass

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def send(self, request, **_kwargs):
            operations.append(request.method)
            if request.method == "DELETE":
                return Response(request, 200, {"deleted": True, "name": "futureagi-example", "version": "1"})
            assert request.method == "POST"
            return Response(request, 200, {
                "id": "agent_synthetic", "name": "futureagi-example", "version": "1",
                "object": "agent.version", "created_at": 1,
                "definition": {"kind": "prompt", "model": "deployment",
                               "instructions": "Answer geography questions in one sentence."},
            })

    model_requests = []

    def model_response(request):
        model_requests.append(request)
        body = json.loads(request.content)
        assert body["agent_reference"]["name"] == "futureagi-example"
        assert body["agent_reference"]["version"] == "1"
        if mode == "error":
            return httpx.Response(400, json={"error": {"message": "synthetic invalid request", "type": "invalid_request_error"}})
        return httpx.Response(200, json={
            "id": "resp_synthetic", "object": "response", "created_at": 1,
            "model": "served-model", "status": "completed", "parallel_tool_calls": True,
            "tool_choice": "auto", "tools": [],
            "output": [{"id": "msg_synthetic", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text", "text": "Paris.", "annotations": []}]}],
            "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7,
                      "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens_details": {"reasoning_tokens": 0}},
        })

    original_init = openai.OpenAI.__init__
    original_project_init = AIProjectClient.__init__

    def project_init(self, *args, **kwargs):
        original_project_init(self, *args, transport=Transport(), **kwargs)

    def client_init(self, *args, **kwargs):
        # Leave get_openai_client() and its native propagation wrapper intact.
        # Swap transport before the wrapper attaches its request hooks.
        kwargs["http_client"] = httpx.Client(
            transport=httpx.MockTransport(model_response), trust_env=False,
        )
        kwargs["max_retries"] = 0
        original_init(self, *args, **kwargs)

    code = re.findall(r"```python\n(.*?)```", PAGE.read_text(), re.S)
    assert len(code) == 1, "Keep one complete executable application example"
    code = code[0]
    if mode == "missing":
        # Reproduce exporter-only setup: no native GenAI instrumentation.
        start = code.index("AIProjectInstrumentor().instrument(")
        end = code.index("\n\ntry:", start)
        code = code[:start] + code[end:]
    elif mode == "content":
        code = code.replace("enable_content_recording=False", "enable_content_recording=True")
    elif mode == "duplicate":
        code = code.replace("\ntry:\n", "\nfrom traceai_openai import OpenAIInstrumentor\nOpenAIInstrumentor().instrument(tracer_provider=provider)\n\ntry:\n", 1)

    try:
        with patch("azure.identity.DefaultAzureCredential", Credential), \
             patch.object(AIProjectClient, "__init__", project_init), \
             patch.object(openai.OpenAI, "__init__", client_init), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                exec(compile(code, str(PAGE), "exec"), {"__name__": "foundry_guide"})
            except openai.BadRequestError:
                assert mode == "error"
            else:
                assert mode != "error", "Expected a synthetic model error"
    finally:
        # Flush the collector's batch processor before closing the OTLP sink.
        collector.terminate()
        collector_log = collector.communicate(timeout=15)[0]
        config_file.close()
        server.shutdown()
        server.server_close()
        thread.join()
    assert collector.returncode == 0, collector_log

    assert operations == ["POST", "DELETE"], operations
    assert len(model_requests) == 1
    assert requests and all(path == "/tracer/v1/traces" for path, _ in requests), requests
    for _, headers in requests:
        headers = {k.lower(): v for k, v in headers.items()}
        assert headers["x-api-key"] == "synthetic-fi-key"
        assert headers["x-secret-key"] == "synthetic-fi-secret"

    spans = []
    for batch in batches:
        for resource in batch.resource_spans:
            attrs = {a.key: a.value.string_value for a in resource.resource.attributes}
            assert attrs["project_name"] == "foundry-offline"
            assert attrs["project_type"] == "observe"
            for scope in resource.scope_spans:
                spans.extend(scope.spans)
    parent = next(s for s in spans if s.name == "foundry-question")
    assert all(s.trace_id == parent.trace_id for s in spans)
    attrs = lambda s: {a.key: (a.value.string_value if a.value.WhichOneof("value") == "string_value" else a.value.int_value) for a in s.attributes}
    chat = [s for s in spans if attrs(s).get("gen_ai.operation.name") in ("chat", "invoke_agent")]
    creation = [s for s in spans if attrs(s).get("gen_ai.operation.name") == "create_agent"]
    wire = b"".join(batch.SerializeToString() for batch in batches)
    if mode == "missing":
        assert not chat and not creation
    else:
        assert len(creation) == 1
        native_chat = [s for s in chat if s.name.startswith("invoke_agent ")]
        assert len(native_chat) == 1, [s.name for s in spans]
        span = native_chat[0]
        # Shared traces and parentage survive both Azure SDK and HTTP spans.
        assert span.parent_span_id == parent.span_id or mode == "duplicate"
        assert creation[0].parent_span_id == parent.span_id
        assert attrs(creation[0])["gen_ai.request.model"] == "deployment"
        assert attrs(span)["gen_ai.provider.name"] == "microsoft.foundry"
        assert attrs(span)["fi.span.kind"] == "AGENT"
        assert attrs(creation[0])["fi.span.kind"] == "AGENT"
        if mode == "error":
            assert span.status.code == 2
        else:
            assert attrs(span)["gen_ai.response.model"] == "served-model"
            assert attrs(span)["gen_ai.usage.input_tokens"] == 5
            assert attrs(span)["gen_ai.usage.output_tokens"] == 2
        assert "traceparent" in model_requests[0].headers
        assert "baggage" not in model_requests[0].headers
        if mode == "duplicate":
            assert any(s.name == "Response" for s in spans), [s.name for s in spans]
        else:
            assert len(chat) == 1
        if mode in ("native", "error"):
            for value in (b"What is the capital of France?", b"Paris.", b"Answer geography questions in one sentence."):
                assert value not in wire
        elif mode == "content":
            assert b"What is the capital of France?" in wire
            assert b"Paris." in wire

    result = {
        "mode": mode,
        "packages": {p: importlib.metadata.version(p) for p in (
            "azure-ai-projects", "openai", "fi-instrumentation-otel", "azure-core-tracing-opentelemetry")},
        "paths": [path for path, _ in requests],
        "spans": [{"name": s.name, "attributes": attrs(s), "status": s.status.code} for s in spans],
        "otlp": [MessageToDict(b) for b in batches],
    }
    return result


if __name__ == "__main__":
    result = probe(sys.argv[1])
    rendered = json.dumps(result, indent=2)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(rendered + "\n")
    print(rendered)
