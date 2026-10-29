#!/usr/bin/env python3
"""Loopback OTLP/HTTP receiver that records what goose exports.

goose exports OTLP/HTTP protobuf. This receiver accepts POST /v1/traces on
127.0.0.1, decodes the payload, and writes a sanitized summary: span names,
parent span names, and attribute keys. Values are kept only for a short
allowlist of structural attributes (operation name, tool name, provider,
model). Everything else, including prompts, tool arguments, tool results,
session ids, user and host names, is reduced to "<present>".

Used to record the pinned-version fixture and to check, without Future AGI
or any network, that a goose build does not export content by default.

Usage:
  record_otlp.py --port 4319 --out fixtures/goose-default.json --seconds 120
  (then run goose with OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4319/v1/traces)

Needs `pip install opentelemetry-proto`.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Attributes whose values are structural, never user content.
KEEP_VALUES = {
    "gen_ai.operation.name",
    "gen_ai.tool.name",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.agent.name",
    "gen_ai.request.stream",
    "session.agent_type",
    "service.name",
    "service.namespace",
    "service.version",
    "project_type",
}

# Attributes that carry prompts, responses, tool arguments, or tool results
# when goose's content flag is on.
CONTENT_KEYS = {
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "input",
    "output",
    "trace_input",
    "trace_output",
    "user_message",
}


def _value(any_value: Any) -> Any:
    kind = any_value.WhichOneof("value")
    return getattr(any_value, kind) if kind else None


def _attrs(pb_attrs) -> dict[str, Any]:
    return {kv.key: _value(kv.value) if kv.key in KEEP_VALUES else "<present>" for kv in pb_attrs}


def summarize(requests) -> dict[str, Any]:
    """Reduce ExportTraceServiceRequests to one content-free summary."""
    resource_keys: set[str] = set()
    names_by_id: dict[bytes, str] = {}
    raw: list[tuple[Any, str]] = []
    for request in requests:
        for rs in request.resource_spans:
            resource_keys.update(kv.key for kv in rs.resource.attributes)
            for ss in rs.scope_spans:
                for span in ss.spans:
                    names_by_id[span.span_id] = span.name
                    raw.append((span, ss.scope.name))
    trace_ids = sorted({span.trace_id.hex() for span, _ in raw})
    spans: list[dict[str, Any]] = []
    for span, scope in sorted(raw, key=lambda item: item[0].start_time_unix_nano):
        spans.append({
            "name": span.name,
            "parent": names_by_id.get(span.parent_span_id, "<not exported>") if span.parent_span_id else "",
            "scope": scope,
            "trace": trace_ids.index(span.trace_id.hex()),
            "status_code": span.status.code,
            "attributes": dict(sorted(_attrs(span.attributes).items())),
            "event_count": len(span.events),
        })
    return {"resource_attribute_keys": sorted(resource_keys), "trace_count": len(trace_ids), "spans": spans}


def main() -> int:
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4319)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=int, default=120, help="stop after this long")
    a = ap.parse_args()

    requests: list[Any] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.path.rstrip("/").endswith("/v1/traces"):
                req = trace_service_pb2.ExportTraceServiceRequest()
                req.ParseFromString(body)
                requests.append(req)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.end_headers()
            self.wfile.write(trace_service_pb2.ExportTraceServiceResponse().SerializeToString())

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", a.port), Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"listening on http://127.0.0.1:{a.port}/v1/traces for {a.seconds}s", flush=True)
    time.sleep(a.seconds)
    server.shutdown()
    summary = summarize(requests)
    with open(a.out, "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"wrote {a.out} ({len(summary['spans'])} spans, {summary['trace_count']} traces, {len(requests)} requests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
