"""Opt-in: what the real Helicone AI Gateway does with `telemetry.exporter: otlp`.

Set HELICONE_GATEWAY_BIN to the ai-gateway binary (run_e2e.sh step 2 writes its path to
$E2E_WORKDIR/gw-bin.path) and install grpcio (in requirements.txt). Skipped otherwise.

No network: the gateway's upstream is a local OpenAI-compatible stub and its OTLP export goes to a local
gRPC receiver. Measured on 0.2.0-beta.30:
  * with `otlp-endpoint: http://127.0.0.1:PORT` it sends OTLP/gRPC trace exports carrying the
    OTEL_EXPORTER_OTLP_HEADERS headers and the OTEL_RESOURCE_ATTRIBUTES resource attributes; the spans
    are pipeline spans with no gen_ai./llm. attributes, and service.name stays "ai-gateway";
  * with `otlp-endpoint: 127.0.0.1:PORT` (no scheme) it serves the request and exports nothing.
"""
import json
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

GATEWAY_BIN = os.environ.get("HELICONE_GATEWAY_BIN")
pytestmark = pytest.mark.skipif(not GATEWAY_BIN, reason="set HELICONE_GATEWAY_BIN to the real ai-gateway binary")

PROJECT = "helicone-gateway-otlp-real"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Upstream:
    """Minimal OpenAI-compatible upstream for the gateway's openai provider."""

    def __enter__(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = json.dumps({
                    "id": "chatcmpl-stub", "object": "chat.completion", "created": int(time.time()), "model": "stub-model",
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "hi"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


class _GrpcTraceReceiver:
    """Local OTLP/gRPC TraceService that keeps metadata, resource attributes and spans of every export."""

    def __enter__(self):
        import grpc  # pip install grpcio
        from concurrent import futures
        from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc

        self.exports = []
        receiver = self

        class Svc(trace_service_pb2_grpc.TraceServiceServicer):
            def Export(self, request, context):
                spans = []
                resources = []
                for rs in request.resource_spans:
                    resources.append({kv.key: kv.value.string_value for kv in rs.resource.attributes})
                    for ss in rs.scope_spans:
                        spans += [{"name": s.name, "attributes": [kv.key for kv in s.attributes]} for s in ss.spans]
                receiver.exports.append(
                    {"metadata": dict(context.invocation_metadata()), "resources": resources, "spans": spans}
                )
                return trace_service_pb2.ExportTraceServiceResponse()

        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(Svc(), self.server)
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()
        return self

    def __exit__(self, *exc):
        self.server.stop(0)


def _run_gateway(tmp_path, endpoint, upstream_url):
    port = _free_port()
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        f'server:\n  address: "127.0.0.1"\n  port: {port}\n'
        f'telemetry:\n  level: "info"\n  exporter: "otlp"\n  otlp-endpoint: "{endpoint}"\n'
        f'providers:\n  openai:\n    base-url: "{upstream_url}"\n    models:\n      - stub-model\n'
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("OTEL_")}
    env.update(
        OPENAI_API_KEY="stub-upstream-key",
        OTEL_EXPORTER_OTLP_HEADERS="x-api-key=real-test-api-key,x-secret-key=real-test-secret-key",
        OTEL_RESOURCE_ATTRIBUTES=f"project_name={PROJECT},project_type=observe",
        OTEL_SERVICE_NAME="not-applied-by-the-gateway",
    )
    log = open(tmp_path / "gateway.log", "w")
    gw = subprocess.Popen([GATEWAY_BIN, "-c", str(cfg)], env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                break
            except OSError:
                assert gw.poll() is None, (tmp_path / "gateway.log").read_text()[-2000:]
                time.sleep(0.25)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/ai/chat/completions",
            data=json.dumps({"model": "openai/stub-model", "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        status = urllib.request.urlopen(req, timeout=30).status
        time.sleep(2)
    finally:
        gw.send_signal(signal.SIGTERM)  # the gateway's shutdown sends the spans it still holds
        gw.wait(timeout=30)
        log.close()
    time.sleep(1)
    return status


def test_endpoint_with_scheme_exports_traces_with_headers_and_project(tmp_path):
    with _Upstream() as up, _GrpcTraceReceiver() as rx:
        status = _run_gateway(tmp_path, f"http://127.0.0.1:{rx.port}", up.url)
    assert status == 200
    assert rx.exports, "the gateway sent no OTLP/gRPC trace export"
    for export in rx.exports:
        assert export["metadata"].get("x-api-key") == "real-test-api-key"
        assert export["metadata"].get("x-secret-key") == "real-test-secret-key"
        for res in export["resources"]:
            assert res.get("project_name") == PROJECT
            assert res.get("project_type") == "observe"
            assert res.get("service.name") == "ai-gateway"
    spans = [s for e in rx.exports for s in e["spans"]]
    assert "request" in {s["name"] for s in spans}
    assert not [k for s in spans for k in s["attributes"] if k.startswith(("gen_ai.", "llm."))]


def test_endpoint_without_scheme_exports_nothing(tmp_path):
    with _Upstream() as up, _GrpcTraceReceiver() as rx:
        status = _run_gateway(tmp_path, f"127.0.0.1:{rx.port}", up.url)
    assert status == 200  # the gateway works normally, so nothing points at the misconfiguration
    assert rx.exports == []
