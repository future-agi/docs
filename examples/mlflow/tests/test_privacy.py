"""Native MLflow -> released Collector -> localhost OTLP wire regressions.

Set OTELCOL_CONTRIB to the 0.164.0 binary. Run under an outbound-deny sandbox
with loopback allowed. No credentials, provider APIs or Future AGI backend.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.trace.v1.trace_pb2 import Status
import pytest
import yaml

EXAMPLE = Path(__file__).resolve().parents[1]
PAGE = EXAMPLE.parents[1] / "src/pages/docs/integrations/mlflow.mdx"
PRIVATE = b"PRIVATE-MLFLOW-CONTENT"


@contextmanager
def capture_server():
    records = []
    received = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            records.append((self.path, dict(self.headers), body))
            received.set()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/tracer/v1/traces", records, received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def decode(records):
    requests = []
    for _, _, body in records:
        request = ExportTraceServiceRequest()
        request.ParseFromString(body)
        requests.append(request)
    return requests


def spans(requests):
    return [span for request in requests for resource in request.resource_spans
            for scope in resource.scope_spans for span in scope.spans]


def attrs(items):
    return {item.key: getattr(item.value, item.value.WhichOneof("value")) for item in items}


def isolated_env(home):
    # Do not inherit endpoints, tracking destinations, proxies or credentials.
    return {"PATH": os.defpath, "HOME": str(home), "NO_PROXY": "127.0.0.1,localhost"}


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    home = tmp_path_factory.mktemp("mlflow-home")
    with capture_server() as (endpoint, records, received):
        env = isolated_env(home) | {
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": endpoint,
            "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
            "OTEL_RESOURCE_ATTRIBUTES": "private.resource=PRIVATE-MLFLOW-CONTENT",
            "OTEL_SERVICE_NAME": "PRIVATE-MLFLOW-CONTENT",
            "MLFLOW_ENABLE_OTEL_GENAI_SEMCONV": "true",
            "MLFLOW_DISABLE_TELEMETRY": "true",
            "MLFLOW_MODEL_CATALOG_URI": "",
            "MLFLOW_TRACE_ENABLE_OTLP_DUAL_EXPORT": "false",
        }
        run = subprocess.run([sys.executable, "-I", str(EXAMPLE / "tests/emit_traces.py")],
                             env=env, cwd=home, capture_output=True, timeout=45)
        assert run.returncode == 0, run.stderr.decode()
        assert received.wait(5), run.stderr.decode()
        requests = decode(records)
    assert len(spans(requests)) == 4, run.stderr.decode()
    assert any(PRIVATE in request.SerializeToString() for request in requests)
    return requests


@contextmanager
def collector(tmp_path, endpoint, *, broken=False):
    binary = os.environ.get("OTELCOL_CONTRIB")
    if not binary:
        pytest.fail("Set OTELCOL_CONTRIB to the released 0.164.0 collector binary")
    version = subprocess.check_output([binary, "--version"], text=True)
    assert "0.164.0" in version
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = yaml.safe_load((EXAMPLE / "otelcol.yaml").read_text())
    config["receivers"]["otlp"]["protocols"]["http"]["endpoint"] = f"127.0.0.1:{port}"
    if broken:
        # Valid OTTL syntax with a deterministic runtime error. The complete
        # batch must be rejected, not forwarded after an ignored error.
        config["processors"]["transform/privacy"]["trace_statements"][-1]["statements"].insert(
            0, 'set(span.attributes["forced_failure"], ParseJSON("not-json"))')
    filename = tmp_path / "collector.yaml"
    filename.write_text(yaml.safe_dump(config))
    env = isolated_env(tmp_path) | {
        "FI_PROJECT_NAME": "mlflow-privacy-test", "FI_TRACES_ENDPOINT": endpoint,
        "FI_API_KEY": "synthetic-api-key", "FI_SECRET_KEY": "synthetic-secret-key",
    }
    subprocess.run([binary, "validate", "--config", str(filename)], env=env,
                   check=True, capture_output=True, timeout=10)
    with (tmp_path / "collector.log").open("w+") as log:
        process = subprocess.Popen([binary, "--config", str(filename)], env=env,
                                   cwd=tmp_path, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 10
            while True:
                assert process.poll() is None, "Collector exited before listening"
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    assert time.monotonic() < deadline, "Collector did not start"
                    time.sleep(0.05)
            yield f"http://127.0.0.1:{port}/v1/traces"
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.seek(0)
            assert PRIVATE.decode() not in log.read(), "Collector logged trace content"


def send(endpoint, request):
    data = urllib.request.Request(endpoint, data=request.SerializeToString(),
                                  headers={"Content-Type": "application/x-protobuf"})
    try:
        with urllib.request.urlopen(data, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_page_has_no_customer_maintained_privacy_code():
    text = PAGE.read_text()
    assert "._span" not in text
    assert "._events" not in text
    assert "span_processors=" not in text
    assert "application process" in text
    assert "127.0.0.1:4318" in text


def test_config_is_traces_only_fail_closed_and_loopback():
    config = yaml.safe_load((EXAMPLE / "otelcol.yaml").read_text())
    assert config["receivers"]["otlp"]["protocols"] == {"http": {"endpoint": "127.0.0.1:4318"}}
    assert config["processors"]["transform/privacy"]["error_mode"] == "propagate"
    assert config["service"]["pipelines"] == {"traces": {
        "receivers": ["otlp"], "processors": ["filter/privacy", "transform/privacy", "batch"],
        "exporters": ["otlp_http/futureagi"],
    }}
    assert set(config["exporters"]) == {"otlp_http/futureagi"}
    assert config["service"]["telemetry"]["logs"]["level"] == "warn"


def test_native_export_contains_content_before_trusted_local_filter(native):
    before = spans(native)
    model = next(span for span in before if attrs(span.attributes).get("gen_ai.operation.name") == "chat")
    assert attrs(model.attributes)["gen_ai.request.model"] == "gpt-4o-mini"
    assert attrs(model.attributes)["gen_ai.usage.input_tokens"] == 11
    assert attrs(model.attributes)["gen_ai.usage.output_tokens"] == 4
    assert any(span.events for span in before)
    assert any(span.status.code == Status.STATUS_CODE_ERROR for span in before)


def test_collector_wire_privacy_model_tokens_and_hierarchy(native, tmp_path):
    request = ExportTraceServiceRequest()
    for part in native:
        request.resource_spans.extend(part.resource_spans)
    # Exercise additional public OTLP fields, not MLflow/SDK private storage.
    for resource in request.resource_spans:
        for scope in resource.scope_spans:
            scope.scope.name = PRIVATE.decode()
            scope.scope.version = PRIVATE.decode()
            scope.scope.attributes.add(key="private.scope").value.string_value = PRIVATE.decode()
            for span in scope.spans:
                span.trace_state = "private=" + PRIVATE.decode()
    # Provider is optional in native MLflow output; preserve it when supplied.
    for span in spans([request]):
        if attrs(span.attributes).get("gen_ai.operation.name") == "chat":
            span.attributes.add(key="gen_ai.provider.name").value.string_value = "openai"
    before = {span.span_id: span for span in spans([request])}
    with capture_server() as (sink, records, received):
        with collector(tmp_path, sink) as endpoint:
            assert send(endpoint, request) == 200
            assert received.wait(5)
        after_requests = decode(records)
        for path, headers, body in records:
            assert path == "/tracer/v1/traces"
            assert {key.lower(): value for key, value in headers.items()}["x-api-key"] == "synthetic-api-key"
            assert {key.lower(): value for key, value in headers.items()}["x-secret-key"] == "synthetic-secret-key"
            assert PRIVATE not in body
    after = spans(after_requests)
    assert len(after) == len(before) == 4  # no duplicate instrumentation
    assert {span.span_id for span in after} == set(before)
    for resource in (r for req in after_requests for r in req.resource_spans):
        assert attrs(resource.resource.attributes) == {
            "project_name": "mlflow-privacy-test", "project_type": "observe",
            "service.name": "mlflow-privacy-test",
        }
        for scope in resource.scope_spans:
            assert scope.scope.name == "mlflow"
            assert not scope.scope.version and not scope.scope.attributes
    for span in after:
        original = before[span.span_id]
        assert (span.trace_id, span.parent_span_id, span.start_time_unix_nano,
                span.end_time_unix_nano, span.status.code, span.kind) == (
                    original.trace_id, original.parent_span_id, original.start_time_unix_nano,
                    original.end_time_unix_nano, original.status.code, original.kind)
        assert not span.events and not span.links and not span.status.message and not span.trace_state
        assert set(attrs(span.attributes)) <= {
            "gen_ai.operation.name", "gen_ai.request.model", "gen_ai.response.model",
            "gen_ai.provider.name", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
        }
        assert span.name == attrs(span.attributes).get("gen_ai.operation.name", "mlflow")
    model = next(span for span in after if span.name == "chat")
    assert attrs(model.attributes)["gen_ai.request.model"] == "gpt-4o-mini"
    assert attrs(model.attributes)["gen_ai.provider.name"] == "openai"
    assert attrs(model.attributes)["gen_ai.usage.input_tokens"] == 11
    assert attrs(model.attributes)["gen_ai.usage.output_tokens"] == 4


def test_documented_example_exports_nested_spans(tmp_path):
    source = PAGE.read_text().split("```python\n", 1)[1].split("```", 1)[0]
    with capture_server() as (sink, records, received):
        with collector(tmp_path, sink) as endpoint:
            env = isolated_env(tmp_path) | {
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": endpoint,
                "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
                "MLFLOW_ENABLE_OTEL_GENAI_SEMCONV": "true",
                "MLFLOW_DISABLE_TELEMETRY": "true", "MLFLOW_MODEL_CATALOG_URI": "",
                "MLFLOW_TRACE_ENABLE_OTLP_DUAL_EXPORT": "false",
            }
            run = subprocess.run([sys.executable, "-I", "-c", source], env=env,
                                 cwd=tmp_path, capture_output=True, timeout=45)
            assert run.returncode == 0, run.stderr.decode()
            assert received.wait(5)
        exported = spans(decode(records))
        assert len(exported) == 2
        root = next(span for span in exported if not span.parent_span_id)
        tool = next(span for span in exported if span.parent_span_id)
        assert root.name == "CHAIN" and tool.name == "execute_tool"
        assert tool.parent_span_id == root.span_id and tool.trace_id == root.trace_id
        assert all(b"headphones" not in body for _, _, body in records)


def test_transform_error_rejects_payload_without_export(native, tmp_path):
    with capture_server() as (sink, records, received):
        with collector(tmp_path, sink, broken=True) as endpoint:
            assert send(endpoint, native[0]) >= 400
        assert not records


def test_linked_spans_are_excluded_instead_of_leaking_link_attributes(native, tmp_path):
    request = ExportTraceServiceRequest()
    request.CopyFrom(native[0])
    for span in spans([request]):
        link = span.links.add(trace_id=b"1" * 16, span_id=b"2" * 8)
        link.attributes.add(key="private.link").value.string_value = PRIVATE.decode()
    with capture_server() as (sink, records, received):
        with collector(tmp_path, sink) as endpoint:
            assert send(endpoint, request) == 200
        assert not records


def test_unknown_operation_cannot_become_content_in_span_name(native, tmp_path):
    request = ExportTraceServiceRequest()
    request.CopyFrom(native[0])
    for span in spans([request]):
        for attribute in span.attributes:
            if attribute.key == "gen_ai.operation.name":
                attribute.value.string_value = PRIVATE.decode()
    with capture_server() as (sink, records, received):
        with collector(tmp_path, sink) as endpoint:
            assert send(endpoint, request) == 200
            assert received.wait(5)
        assert all(PRIVATE not in body for _, _, body in records)
        for span in spans(decode(records)):
            assert span.name == "mlflow"
            assert "gen_ai.operation.name" not in attrs(span.attributes)
