"""Shared fixtures: a fake OpenAI endpoint, a recording OTLP collector, and a runner that
launches ../app.py as a customer would (a separate process, real AgentScope)."""

from __future__ import annotations

import getpass
import gzip
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from fake_openai import FakeOpenAI  # noqa: E402

import importlib.metadata  # noqa: E402

AGENTSCOPE_VERSION = importlib.metadata.version("agentscope")
AGENTSCOPE_1X = AGENTSCOPE_VERSION.startswith("1.")

MODEL_KEY = "test-model-key-0001"
FI_API_KEY = "test-fi-api-key-0002"
FI_SECRET_KEY = "test-fi-secret-key-0003"
MARKER = "ZQX7-MARKER-4471"


class Collector:
    """Records every OTLP/HTTP export it receives, as fi-collector would see it."""

    def __init__(self) -> None:
        self.exports: list[dict] = []
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

    def close(self) -> None:
        self.server.shutdown()

    def requests(self) -> list[dict]:
        out = []
        for e in self.exports:
            body = e["body"]
            if e["headers"].get("content-encoding") == "gzip":
                body = gzip.decompress(body)
            msg = trace_service_pb2.ExportTraceServiceRequest()
            msg.ParseFromString(body)
            out.append(MessageToDict(msg, preserving_proto_field_name=True))
        return out

    def spans(self) -> list[dict]:
        found = []
        for req in self.requests():
            for rs in req.get("resource_spans", []):
                resource = {a["key"]: _any(a["value"]) for a in rs.get("resource", {}).get("attributes", [])}
                for ss in rs.get("scope_spans", []):
                    for sp in ss.get("spans", []):
                        sp = dict(sp)
                        sp["_resource"] = resource
                        sp["_scope"] = ss.get("scope", {})
                        sp["_attrs"] = {a["key"]: _any(a["value"]) for a in sp.get("attributes", [])}
                        found.append(sp)
        return found

    def everything(self) -> str:
        """Every byte the collector received, as text, for a marker search."""
        parts = [e["body"].decode("utf-8", "replace") for e in self.exports]
        parts += [json.dumps(r, ensure_ascii=False) for r in self.requests()]
        parts += [json.dumps(e["headers"]) + e["path"] for e in self.exports]
        return "\n".join(parts)


def _any(value: dict):
    if "int_value" in value:  # protobuf JSON carries 64-bit integers as strings
        return int(value["int_value"])
    for k in ("string_value", "double_value", "bool_value"):
        if k in value:
            return value[k]
    return json.dumps(value)


def by_name(spans: list[dict], prefix: str) -> list[dict]:
    return [s for s in spans if s["name"].startswith(prefix)]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def model():
    server = FakeOpenAI(api_key=MODEL_KEY)
    yield server
    server.close()


@pytest.fixture()
def collector():
    c = Collector()
    yield c
    c.close()


@pytest.fixture()
def run_app(model, collector):
    def _run(*args, env=None, fi_base_url=None, script="app.py"):
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OPENAI", "OTEL_"))}
        clean.update(
            {
                "OPENAI_API_KEY": MODEL_KEY,
                "OPENAI_BASE_URL": model.url,
                "OPENAI_MODEL": "fake-model",
                "FI_API_KEY": FI_API_KEY,
                "FI_SECRET_KEY": FI_SECRET_KEY,
                "FI_BASE_URL": fi_base_url or collector.url,
                "FI_PROJECT_NAME": "agentscope-test",
                "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        clean.update(env or {})
        return subprocess.run(
            [sys.executable, str(ROOT / script), *args],
            cwd=ROOT,
            env=clean,
            capture_output=True,
            text=True,
            timeout=120,
        )

    return _run


@pytest.fixture()
def machine_identifiers():
    """Strings that identify this machine and must never be exported."""
    return {
        "username": getpass.getuser(),
        "hostname": socket.gethostname(),
        "repo path": str(ROOT),
        "home": str(Path.home()),
        "python path": sys.prefix,
    }


def pytest_collection_modifyitems(config, items):
    """The 2.x tests need AgentScope 2.x and the 1.x test needs 1.x: one environment runs one set."""
    skip_2x = pytest.mark.skip(reason=f"AgentScope {AGENTSCOPE_VERSION} is a 1.x release; see test_legacy_1x.py")
    skip_1x = pytest.mark.skip(reason=f"AgentScope {AGENTSCOPE_VERSION} is a 2.x release; test_legacy_1x.py needs 1.x")
    for item in items:
        is_legacy = item.fspath.basename == "test_legacy_1x.py"
        if AGENTSCOPE_1X and not is_legacy:
            item.add_marker(skip_2x)
        elif not AGENTSCOPE_1X and is_legacy:
            item.add_marker(skip_1x)
