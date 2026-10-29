import importlib
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import tracing  # noqa: E402


class FakeContext:
    def __init__(self, remaining_ms=30_000, request_id="req-0001"):
        self.aws_request_id = request_id
        self._remaining = remaining_ms

    def get_remaining_time_in_millis(self):
        return self._remaining


class RecordingExporter(SpanExporter):
    """Fake exporter: records what was exported and when (as an ordered event log)."""

    def __init__(self, log):
        self.log = log
        self.batches = []

    def export(self, spans):
        self.batches.append(list(spans))
        self.log.append(("export", [s.name for s in spans]))
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True

    @property
    def spans(self):
        return [s for b in self.batches for s in b]


class Collector:
    """A local OTLP/HTTP receiver that records requests (headers + decoded protobuf)."""

    def __init__(self, status=200, delay=0.0):
        self.requests, self.status, self.delay = [], status, delay
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length", 0))
                body = self.rfile.read(n)
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                if outer.delay:
                    import time
                    time.sleep(outer.delay)
                self.send_response(outer.status)
                self.send_header("content-length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def decoded(self):
        out = []
        for r in self.requests:
            m = ExportTraceServiceRequest()
            m.ParseFromString(r["body"])
            out.append(m)
        return out

    def span_names(self):
        return [s.name for m in self.decoded() for rs in m.resource_spans for ss in rs.scope_spans for s in ss.spans]

    def close(self):
        self.server.shutdown()


def fixture(name):
    return json.loads((HERE / "fixtures" / name).read_text())


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in ("FI_API_KEY", "FI_SECRET_KEY", "FI_BASE_URL", "FI_PROJECT_NAME", "AWS_LAMBDA_FUNCTION_NAME", "LAMBDA_TRACE_CAPTURE_CONTENT"):
        monkeypatch.delenv(k, raising=False)
    tracing.reset_for_tests()
    yield
    prov = tracing._provider
    tracing.reset_for_tests()
    if prov is not None:
        prov.shutdown()


@pytest.fixture
def load_handler():
    def _load():
        sys.modules.pop("handler", None)
        return importlib.import_module("handler")
    return _load


@pytest.fixture
def collector():
    c = Collector()
    yield c
    c.close()
