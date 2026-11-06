"""A loopback OTLP/HTTP recorder for tests. It keeps every request: path, headers, raw body,
and the decoded spans. It never forwards anything.

It also answers the eval-config check that ``fi_instrumentation.register()`` posts on
start-up, so the recipe runs unchanged against it.
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

TRACE_PATHS = ("/v1/traces", "/tracer/v1/traces")


def _value(value: dict):
    for kind in ("stringValue", "boolValue", "intValue", "doubleValue"):
        if kind in value:
            return int(value[kind]) if kind == "intValue" else value[kind]
    return value


def hex_id(value: str) -> str:
    """Protobuf JSON renders bytes as base64; OTLP ids are read as lower-case hex."""
    return base64.b64decode(value).hex() if value else ""


def flatten(attributes: list) -> dict:
    return {a["key"]: _value(a.get("value", {})) for a in attributes or []}


class Recorder:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                path = self.path.split("?", 1)[0]
                if path.startswith("/tracer/custom-eval-config/"):
                    self._send(200, b'{"result": {"exists": false}}', "application/json")
                    return
                if path not in TRACE_PATHS:
                    self._send(404, b"", "text/plain")
                    return
                request = ExportTraceServiceRequest()
                request.ParseFromString(body)
                with owner._lock:
                    owner.requests.append(
                        {
                            "path": path,
                            "headers": {k.lower(): v for k, v in self.headers.items()},
                            "body": body,
                            "otlp": MessageToDict(request),
                        }
                    )
                self._send(200, b"", "application/x-protobuf")

            def _send(self, code: int, data: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "Recorder":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    # --- views -----------------------------------------------------------------------
    def raw(self) -> bytes:
        """Every exported byte, for substring scans."""
        with self._lock:
            return b"".join(r["body"] for r in self.requests)

    def spans(self) -> list[dict]:
        """Decoded spans with flattened attributes, plus the resource attributes."""
        out = []
        with self._lock:
            for request in self.requests:
                for rs in request["otlp"].get("resourceSpans", []):
                    resource = flatten(rs.get("resource", {}).get("attributes", []))
                    for ss in rs.get("scopeSpans", []):
                        for span in ss.get("spans", []):
                            out.append(
                                {
                                    "name": span["name"],
                                    "traceId": hex_id(span["traceId"]),
                                    "spanId": hex_id(span["spanId"]),
                                    "parentSpanId": hex_id(span.get("parentSpanId", "")),
                                    "attributes": flatten(span.get("attributes", [])),
                                    "events": [
                                        {"name": e.get("name"), "attributes": flatten(e.get("attributes", []))}
                                        for e in span.get("events", [])
                                    ],
                                    "status": span.get("status", {}),
                                    "resource": resource,
                                }
                            )
        return out

    def dump(self) -> str:
        return json.dumps(self.spans(), indent=1, default=str)
