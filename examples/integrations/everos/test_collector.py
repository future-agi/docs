"""Offline native EverOS -> real Collector -> loopback OTLP wire contract.

Install EverOS without its server/model dependencies; this exercises the actual
native tracing modules and HTTP exporter, not a vendor, database or UI.
Run in a network namespace/sandbox that allows loopback only:
  OTELCOL=/absolute/path/otelcol-contrib python -I test_collector.py
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from everos.config.settings import ObservabilitySettings
from everos.core.observability.tracing.attributes import (
    capture_input, capture_output, memory_span, set_generation_usage,
)
from everos.core.observability.tracing.provider import (
    force_flush, init_tracing, shutdown_tracing,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "public/examples/observe/langfuse-native.yaml"
ERROR = "SYNTHETIC_PRIVATE_ERROR"
INPUT = "SYNTHETIC_PRIVATE_INPUT"
OUTPUT = "SYNTHETIC_PRIVATE_OUTPUT"
API_KEY = "synthetic-fi-key"
SECRET_KEY = "synthetic-fi-secret"


def attrs(values):
    def decode(value):
        field = value.WhichOneof("value")
        if field == "array_value":
            return [decode(v) for v in value.array_value.values]
        return getattr(value, field) if field else None
    return {a.key: decode(a.value) for a in values}


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WireContract(unittest.TestCase):
    def setUp(self):
        self.requests = queue.Queue()
        requests = self.requests

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                requests.put((self.path, dict(self.headers), body))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 3)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(shutdown_tracing)
        self.target = f"http://127.0.0.1:{self.server.server_port}/tracer/v1/traces"

    @contextmanager
    def collector(self, capture=None):
        binary = os.environ.get("OTELCOL")
        if not binary:
            self.fail("OTELCOL must name a real otelcol-contrib 0.164.0 binary")
        port = unused_port()
        with tempfile.TemporaryDirectory() as tmp:
            # Do not forward developer/CI credentials, proxy vars or SDK settings.
            env = {"PATH": os.defpath, "HOME": tmp,
                   "FI_TRACES_ENDPOINT": self.target,
                   "FI_API_KEY": API_KEY, "FI_SECRET_KEY": SECRET_KEY,
                   "FI_PROJECT_NAME": "everos-offline",
                   "FI_OTLP_LISTEN": f"127.0.0.1:{port}"}
            if capture is not None:
                env["FI_CAPTURE_CONTENT"] = capture
            with open(Path(tmp) / "collector.log", "w+") as log:
                process = subprocess.Popen([binary, "--config", str(CONFIG)], env=env,
                                           stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 15
                    while True:
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(f"Collector exited: {log.read()}")
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                                break
                        except OSError:
                            if time.monotonic() > deadline:
                                self.fail("Collector did not bind loopback")
                            time.sleep(0.05)
                    yield f"http://127.0.0.1:{port}"
                finally:
                    process.terminate()
                    try:
                        process.wait(10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(5)

    def emit(self, endpoint, capture=False, project=None):
        resource = {"OTEL_RESOURCE_ATTRIBUTES": f"project_name={project}"} if project else {}
        with patch.dict(os.environ, resource, clear=True):
            settings = ObservabilitySettings(enabled=True, endpoint=endpoint,
                                             capture_content=capture, service_name="everos-test")
            self.assertTrue(init_tracing(settings))
            originals = {}
            with memory_span("memory.search", observation_type="span",
                             session_id="session-synthetic", user_id="user-synthetic") as root:
                originals["memory.search"] = root.get_span_context()
                capture_input(root, INPUT)
                capture_output(root, {"memory": OUTPUT})
                for native in ("generation", "embedding", "retriever", "agent", "tool", "future-kind"):
                    with memory_span(native, observation_type=native) as span:
                        originals[native] = span.get_span_context()
                        if native == "generation":
                            set_generation_usage(model="synthetic-model", input_tokens=0, output_tokens=2)
                            set_generation_usage(input_tokens=3, output_tokens=5)
                with memory_span("canonical", observation_type="generation",
                                 session_id="native-session", user_id="native-user") as span:
                    originals["canonical"] = span.get_span_context()
                    span.set_attributes({"gen_ai.span.kind": "AGENT", "session.id": "existing-session",
                                         "user.id": "existing-user", "input.value": INPUT,
                                         "output.value": OUTPUT, "tag.tags": ["existing-tag"]})
                    capture_input(span, "do not overwrite canonical input")
                    capture_output(span, "do not overwrite canonical output")
                try:
                    with memory_span("failure", observation_type="generation") as span:
                        originals["failure"] = span.get_span_context()
                        span.set_attributes({"exception.message": ERROR, "exception.stacktrace": ERROR,
                                             "error.message": ERROR, "error.stack": ERROR,
                                             "langfuse.observation.status_message": ERROR})
                        span.add_event("diagnostic", {"error.message": ERROR, "error.stack": ERROR,
                                                       "diagnostic.code": "synthetic-code"})
                        raise ValueError(ERROR)
                except ValueError:
                    pass
            force_flush()
            shutdown_tracing()
        return originals

    def receive(self):
        path, headers, body = self.requests.get(timeout=15)
        message = ExportTraceServiceRequest.FromString(body)
        spans = {s.name: s for r in message.resource_spans for scope in r.scope_spans for s in scope.spans}
        return path, {k.lower(): v for k, v in headers.items()}, body, message, spans

    def test_direct_route_reproduces_error_leak_and_native_only_fields(self):
        self.emit(self.target)
        _, _, body, _, spans = self.receive()
        self.assertIn(ERROR.encode(), body)
        root = attrs(spans["memory.search"].attributes)
        self.assertNotIn("langfuse.observation.input", root)
        self.assertNotIn("gen_ai.span.kind", root)
        self.assertNotIn("session.id", root)
        self.assertEqual(root["langfuse.session.id"], "session-synthetic")
        self.assertIn(ERROR, spans["failure"].status.message)

    def check_processed(self, source_capture, collector_capture):
        with self.collector(collector_capture) as local:
            original = self.emit(local + "/v1/traces", capture=source_capture)
            path, headers, body, message, spans = self.receive()
        self.assertEqual(path, "/tracer/v1/traces")
        self.assertEqual(headers["x-api-key"], API_KEY)
        self.assertEqual(headers["x-secret-key"], SECRET_KEY)
        self.assertNotIn(API_KEY.encode(), body)
        self.assertNotIn(SECRET_KEY.encode(), body)
        self.assertNotIn(ERROR.encode(), body)
        self.assertEqual(len(spans), len(original))
        root = spans["memory.search"]
        for name, span in spans.items():
            self.assertEqual(span.span_id, original[name].span_id.to_bytes(8, "big"))
            self.assertEqual(span.trace_id, original[name].trace_id.to_bytes(16, "big"))
            self.assertGreaterEqual(span.end_time_unix_nano, span.start_time_unix_nano)
            self.assertEqual(span.parent_span_id, b"" if name == "memory.search" else root.span_id)
        values = attrs(root.attributes)
        self.assertEqual(values["session.id"], "session-synthetic")
        self.assertEqual(values["user.id"], "user-synthetic")
        self.assertEqual(values["tag.tags"], ["everos", "memory"])
        self.assertEqual(values["gen_ai.span.kind"], "CHAIN")
        for native, kind in {"generation": "LLM", "embedding": "EMBEDDING", "retriever": "RETRIEVER",
                             "agent": "AGENT", "tool": "TOOL"}.items():
            self.assertEqual(attrs(spans[native].attributes)["gen_ai.span.kind"], kind)
        self.assertNotIn("gen_ai.span.kind", attrs(spans["future-kind"].attributes))
        generation = attrs(spans["generation"].attributes)
        self.assertEqual(generation["gen_ai.request.model"], "synthetic-model")
        self.assertEqual(generation["gen_ai.usage.input_tokens"], 3)
        self.assertEqual(generation["gen_ai.usage.output_tokens"], 7)
        canonical = attrs(spans["canonical"].attributes)
        self.assertEqual(canonical["gen_ai.span.kind"], "AGENT")
        self.assertEqual(canonical["session.id"], "existing-session")
        self.assertEqual(canonical["user.id"], "existing-user")
        self.assertEqual(canonical["tag.tags"], ["existing-tag"])
        failure = spans["failure"]
        self.assertEqual(failure.status.code, 2)  # STATUS_CODE_ERROR
        self.assertEqual(failure.status.message, "")
        exception = next(e for e in failure.events if e.name == "exception")
        self.assertIn("ValueError", attrs(exception.attributes)["exception.type"])
        diagnostic = next(e for e in failure.events if e.name == "diagnostic")
        self.assertEqual(attrs(diagnostic.attributes), {"diagnostic.code": "synthetic-code"})
        for r in message.resource_spans:
            self.assertEqual(attrs(r.resource.attributes)["project_name"], "everos-offline")
            self.assertEqual(attrs(r.resource.attributes)["project_type"], "observe")
            self.assertEqual(attrs(r.resource.attributes)["service.name"], "everos-test")
        for span in spans.values():
            self.assertNotIn("langfuse.observation.input", attrs(span.attributes))
            self.assertNotIn("langfuse.observation.output", attrs(span.attributes))
        if collector_capture != "true":
            self.assertNotIn(INPUT.encode(), body)
            self.assertNotIn(OUTPUT.encode(), body)
            self.assertNotIn("input.value", values)
            self.assertNotIn("output.value", values)
        elif source_capture:
            self.assertEqual(values["input.value"], INPUT)
            self.assertEqual(json.loads(values["output.value"]), {"memory": OUTPUT})
            self.assertEqual(canonical["input.value"], INPUT)
            self.assertEqual(canonical["output.value"], OUTPUT)
        else:
            self.assertNotIn("input.value", values)
            self.assertNotIn("output.value", values)

    def test_metadata_only_default(self):
        self.check_processed(False, None)

    def test_collector_blocks_accidental_upstream_content_capture(self):
        self.check_processed(True, None)

    def test_content_requires_literal_opt_in(self):
        self.check_processed(True, "TRUE")

    def test_explicit_content_opt_in_keeps_error_text_private(self):
        self.check_processed(True, "true")

    def test_collector_opt_in_cannot_recover_uncaptured_content(self):
        self.check_processed(False, "true")

    def test_existing_project_and_no_logs_or_metrics_export(self):
        with self.collector() as local:
            for signal, data in (
                ("logs", {"resourceLogs": [{"scopeLogs": [{"logRecords": [{"body": {"stringValue": ERROR}}]}]}]}),
                ("metrics", {"resourceMetrics": [{"scopeMetrics": [{"metrics": [{"name": "synthetic", "gauge": {"dataPoints": [{"asInt": "1"}]}}]}]}]}),
            ):
                req = Request(local + "/v1/" + signal, json.dumps(data).encode(),
                              {"Content-Type": "application/json"})
                with urlopen(req, timeout=5) as response:
                    self.assertEqual(response.status, 200)
            self.emit(local + "/v1/traces", project="existing-project")
            _, _, body, message, _ = self.receive()
            self.assertNotIn(ERROR.encode(), body)
            self.assertTrue(self.requests.empty())
            for r in message.resource_spans:
                self.assertEqual(attrs(r.resource.attributes)["project_name"], "existing-project")

    def test_secure_configuration_contract(self):
        import yaml
        config = yaml.safe_load(CONFIG.read_text())
        self.assertEqual(config["processors"]["transform/native"]["error_mode"], "propagate")
        self.assertEqual(config["receivers"]["otlp"]["protocols"]["http"]["endpoint"],
                         "${env:FI_OTLP_LISTEN:-127.0.0.1:4318}")
        self.assertEqual(config["service"]["pipelines"]["traces"]["processors"], ["transform/native", "batch"])
        self.assertNotIn("debug", config["exporters"])


if __name__ == "__main__":
    print(f"EverOS {version('everos')}; OpenTelemetry {version('opentelemetry-sdk')}; loopback-only wire tests", flush=True)
    unittest.main(verbosity=2)
