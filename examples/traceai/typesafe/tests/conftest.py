"""Fixtures: the System One stand-in and a recording OTLP/HTTP collector, both on 127.0.0.1."""

from __future__ import annotations

import gzip
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "standin"))

import systemone_stub  # noqa: E402


@pytest.fixture()
def stub():
    server = systemone_stub.serve(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:{0}".format(server.server_address[1])
    server.shutdown()
    server.server_close()


class Recorder:
    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []

    def spans(self) -> List[Dict[str, Any]]:
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

        found = []
        for request in self.requests:
            message = ExportTraceServiceRequest()
            message.ParseFromString(request["body"])
            for resource_spans in message.resource_spans:
                resource = {kv.key: _value(kv.value) for kv in resource_spans.resource.attributes}
                for scope_spans in resource_spans.scope_spans:
                    for span in scope_spans.spans:
                        found.append(
                            {
                                "name": span.name,
                                "trace_id": span.trace_id.hex(),
                                "span_id": span.span_id.hex(),
                                "parent": span.parent_span_id.hex(),
                                "status": span.status.code,
                                "status_message": span.status.message,
                                "attributes": {kv.key: _value(kv.value) for kv in span.attributes},
                                "events": [[e.name, {kv.key: _value(kv.value) for kv in e.attributes}] for e in span.events],
                                "resource": resource,
                            }
                        )
        return found

    def raw(self) -> bytes:
        return b"".join(request["body"] for request in self.requests)


def _value(value: Any) -> Any:
    kind = value.WhichOneof("value")
    return getattr(value, kind) if kind else None


@pytest.fixture()
def collector():
    recorder = Recorder()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("content-length") or 0))
            if self.headers.get("content-encoding") == "gzip":
                body = gzip.decompress(body)
                recorder.gzip = True
            recorder.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            self.send_response(200)
            self.send_header("content-type", "application/x-protobuf")
            self.send_header("content-length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    recorder.url = "http://127.0.0.1:{0}".format(server.server_address[1])
    yield recorder
    server.shutdown()
    server.server_close()
