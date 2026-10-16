"""A tiny OTLP/HTTP trace receiver for local tests.

It accepts what `register()` sends (POST /tracer/v1/traces, protobuf body),
decodes it, and keeps the decoded spans, the resource attributes, and the
request headers so tests can assert on the wire format. Nothing leaves the
machine.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


def _any_value(v):
    kind = v.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_any_value(x) for x in v.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _any_value(kv.value) for kv in v.kvlist_value.values}
    return getattr(v, kind)


def _attrs(kvs):
    return {kv.key: _any_value(kv.value) for kv in kvs}


class CapturedSpan:
    def __init__(self, resource_attrs, span):
        self.resource = resource_attrs
        self.name = span.name
        self.trace_id = span.trace_id.hex()
        self.span_id = span.span_id.hex()
        self.parent_span_id = span.parent_span_id.hex()
        self.attributes = _attrs(span.attributes)
        self.events = [
            {"name": e.name, "attributes": _attrs(e.attributes)} for e in span.events
        ]
        # OTLP status code: 0 unset, 1 ok, 2 error
        self.status_code = span.status.code
        self.status_message = span.status.message

    def to_dict(self):
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "resource": self.resource,
            "attributes": self.attributes,
            "events": self.events,
            "status_code": self.status_code,
            "status_message": self.status_message,
        }


class OtlpCapture:
    """Context manager: `with OtlpCapture() as cap:` then use `cap.url`."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.spans: list[CapturedSpan] = []
        self.requests: list[dict] = []  # {path, headers, body_len}
        self._lock = threading.Lock()
        capture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def _read_body(self) -> bytes:
                if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                    out = b""
                    while True:
                        size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                        if size == 0:
                            self.rfile.readline()
                            return out
                        out += self.rfile.read(size)
                        self.rfile.readline()
                return self.rfile.read(int(self.headers.get("Content-Length", 0)))

            def do_POST(self):
                body = self._read_body()
                hdrs = {k.lower(): v for k, v in self.headers.items()}
                with capture._lock:
                    capture.requests.append(
                        {"path": self.path, "headers": hdrs, "body_len": len(body)}
                    )
                if hdrs.get("content-encoding"):
                    # Future AGI's collector rejects compressed bodies; mirror that.
                    self.send_response(415)
                    self.end_headers()
                    return
                req = ExportTraceServiceRequest()
                if "json" in (hdrs.get("content-type") or ""):
                    from google.protobuf import json_format

                    json_format.Parse(body, req)  # OTLP/JSON, which the JS exporter sends
                else:
                    req.ParseFromString(body)
                with capture._lock:
                    for rs in req.resource_spans:
                        res = _attrs(rs.resource.attributes)
                        for ss in rs.scope_spans:
                            for sp in ss.spans:
                                capture.spans.append(CapturedSpan(res, sp))
                out = ExportTraceServiceResponse().SerializeToString()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self._server = ThreadingHTTPServer((host, port), Handler)
        self.port = self._server.server_address[1]
        self.url = f"http://{host}:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()

    def wait_for_spans(self, n: int, timeout: float = 10.0):
        import time

        end = time.time() + timeout
        while time.time() < end:
            with self._lock:
                if len(self.spans) >= n:
                    return list(self.spans)
            time.sleep(0.05)
        with self._lock:
            return list(self.spans)
