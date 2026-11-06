"""A loopback OTLP/HTTP trace receiver that records what a client sent.

It stands in for the Future AGI collector in the unit tests: it keeps every request's path,
headers and raw body, and decodes the protobuf into plain dicts for assertions.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


def _any(value) -> object:
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    inner = getattr(value, kind)
    if kind == "array_value":
        return [_any(v) for v in inner.values]
    if kind == "kvlist_value":
        return {kv.key: _any(kv.value) for kv in inner.values}
    return inner


def _attrs(items) -> dict:
    return {kv.key: _any(kv.value) for kv in items}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        self.server.received.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        self.send_response(200)
        self.send_header("content-type", "application/x-protobuf")
        self.send_header("content-length", "0")
        self.end_headers()


class Recorder(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.received: list[dict] = []
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def start(self) -> "Recorder":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()

    def raw_bodies(self) -> list[bytes]:
        return [r["body"] for r in self.received]

    def spans(self) -> list[dict]:
        """Every exported span as a dict: name, ids, kind, status, attributes, events, resource."""
        out: list[dict] = []
        for request in self.received:
            message = ExportTraceServiceRequest()
            message.ParseFromString(request["body"])
            for resource_spans in message.resource_spans:
                resource = _attrs(resource_spans.resource.attributes)
                for scope_spans in resource_spans.scope_spans:
                    for span in scope_spans.spans:
                        out.append(
                            {
                                "name": span.name,
                                "trace_id": span.trace_id.hex(),
                                "span_id": span.span_id.hex(),
                                "parent_span_id": span.parent_span_id.hex(),
                                "kind": span.kind,
                                "status_code": span.status.code,
                                "status_message": span.status.message,
                                "attributes": _attrs(span.attributes),
                                "events": [{"name": e.name, "attributes": _attrs(e.attributes)} for e in span.events],
                                "resource": resource,
                                "scope": scope_spans.scope.name,
                            }
                        )
        return out
