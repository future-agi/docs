"""Shared fixtures: the Vercel-shaped stand-in, a recording OTLP collector, and a
runner that launches ../app.py exactly as a customer would (a separate process)."""
import gzip
import json
import os
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "standin"))
sys.path.insert(0, str(ROOT / "drain"))

import vercel_gateway_stub  # noqa: E402

GATEWAY_KEY = "test-gateway-key-0001"
FI_API_KEY = "test-fi-api-key-0002"
FI_SECRET_KEY = "test-fi-secret-key-0003"
MODEL = "vendor/example-model"


class Collector:
    """Records every OTLP/HTTP trace export it receives, like fi-collector would see it."""

    def __init__(self):
        self.exports = []
        self.lock = threading.Lock()
        collector = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                with collector.lock:
                    collector.exports.append(
                        {"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body}
                    )
                out = trace_service_pb2.ExportTraceServiceResponse().SerializeToString()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()

    # decoded views -----------------------------------------------------------
    def requests(self):
        out = []
        for e in self.exports:
            body = e["body"]
            if e["headers"].get("content-encoding") == "gzip":
                body = gzip.decompress(body)
            msg = trace_service_pb2.ExportTraceServiceRequest()
            msg.ParseFromString(body)
            out.append(MessageToDict(msg, preserving_proto_field_name=True))
        return out

    def spans(self):
        found = []
        for req in self.requests():
            for rs in req.get("resource_spans", []):
                resource = {a["key"]: _any(a["value"]) for a in rs.get("resource", {}).get("attributes", [])}
                for ss in rs.get("scope_spans", []):
                    for sp in ss.get("spans", []):
                        sp = dict(sp)
                        sp["_resource"] = resource
                        sp["_attrs"] = {a["key"]: _any(a["value"]) for a in sp.get("attributes", [])}
                        found.append(sp)
        return found

    def raw_texts(self):
        """Every byte the collector received, as text, for a marker search."""
        return [e["body"].decode("utf-8", "replace") for e in self.exports] + [
            json.dumps(r) for r in self.requests()
        ]


def _any(value):
    for k in ("string_value", "int_value", "double_value", "bool_value"):
        if k in value:
            return value[k]
    return json.dumps(value)


@pytest.fixture()
def stub():
    server = vercel_gateway_stub.serve(api_key=GATEWAY_KEY)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    yield server
    server.shutdown()


@pytest.fixture()
def collector():
    c = Collector()
    yield c
    c.close()


@pytest.fixture()
def run_app(stub, collector):
    def _run(*args, env=None, base_url=None, fi_base_url=None):
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "AI_GATEWAY", "OPENAI", "OTEL_"))}
        clean.update(
            {
                "AI_GATEWAY_API_KEY": GATEWAY_KEY,
                "AI_GATEWAY_MODEL": MODEL,
                "AI_GATEWAY_BASE_URL": base_url or stub.url,
                "FI_API_KEY": FI_API_KEY,
                "FI_SECRET_KEY": FI_SECRET_KEY,
                "FI_BASE_URL": fi_base_url or collector.url,
                "FI_PROJECT_NAME": "vercel-ai-gateway-test",
                "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        clean.update(env or {})
        return subprocess.run(
            [sys.executable, str(ROOT / "app.py"), *args],
            cwd=ROOT,
            env=clean,
            capture_output=True,
            text=True,
            timeout=120,
        )

    return _run


def gateway_requests(stub):
    with urllib.request.urlopen(stub.url.replace("/v1", "") + "/__requests") as r:
        return json.load(r)
