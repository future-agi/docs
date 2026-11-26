#!/usr/bin/env python3
"""Re-encode REAL TrueFoundry gateway spans as an OTLP batch and POST it to Future AGI.

The spans come from TrueFoundry's own Query Spans API (`POST /api/svc/v1/spans/query`), so
names, ids, parent links, status and attributes are what a real gateway produced. They are NOT
what the gateway's OTEL exporter sent: a Developer-plan tenant cannot enable the exporter (HTTP 402,
`settings.otelConfig`, upgrade to PRO). The query API returns no resource attributes, no span events
and no trace state, so this script adds the resource itself (`service.name=tfy-llm-gateway` plus the
`--resource` pairs you give it).

  tfy_spans.py-style use:
    curl -s -H "Authorization: Bearer $TFY_API_KEY" -H 'Content-Type: application/json' \\
      -d '{"dataRoutingDestination":"default","startTime":"2026-10-20T00:00:00.000Z","limit":100}' \\
      https://<tenant>.truefoundry.cloud/api/svc/v1/spans/query > spans.json
    FI_API_KEY=... FI_SECRET_KEY=... replay_spans.py spans.json --url http://localhost:14338/v1/traces \\
      --resource project_name=my-project --resource project_type=observe --trace-id <id> [--drop-content]

Never prints keys or span content.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, KeyValue, KeyValueList
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span, Status

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KINDS = {"Internal": Span.SPAN_KIND_INTERNAL, "Server": Span.SPAN_KIND_SERVER, "Client": Span.SPAN_KIND_CLIENT,
         "Producer": Span.SPAN_KIND_PRODUCER, "Consumer": Span.SPAN_KIND_CONSUMER}
STATUS = {"Unset": Status.STATUS_CODE_UNSET, "Ok": Status.STATUS_CODE_OK, "Error": Status.STATUS_CODE_ERROR}
CONTENT_KEYS = ("tfy.input", "tfy.output", "tfy.input_short_hand")


def _val(v) -> AnyValue:
    if isinstance(v, bool):
        return AnyValue(bool_value=v)
    if isinstance(v, int):
        return AnyValue(int_value=v)
    if isinstance(v, float):
        return AnyValue(double_value=v)
    if isinstance(v, (list, tuple)):
        return AnyValue(array_value=ArrayValue(values=[_val(x) for x in v]))
    if isinstance(v, dict):  # the query API returns tfy.request.metadata as an object
        return AnyValue(kvlist_value=KeyValueList(values=[KeyValue(key=k, value=_val(x)) for k, x in v.items()]))
    return AnyValue(string_value=str(v))


def _ns(ts: str) -> int:
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1_000_000_000)


def build_request(
    rows: List[dict],
    *,
    trace_ids: Optional[List[str]] = None,
    resource: Optional[Dict[str, str]] = None,
    drop_content: bool = False,
) -> ExportTraceServiceRequest:
    """One ResourceSpans, one ScopeSpans per instrumentation scope, for the chosen traces."""
    chosen = [r for r in rows if not trace_ids or r["traceId"] in trace_ids]
    attrs = {"service.name": "tfy-llm-gateway", **(resource or {})}
    by_scope: Dict[str, ScopeSpans] = {}
    for r in chosen:
        scope = by_scope.setdefault(r.get("scopeName", ""), ScopeSpans())
        scope.scope.name = r.get("scopeName", "")
        scope.scope.version = r.get("scopeVersion", "") or ""
        start = _ns(r["timestamp"])
        span = Span(
            trace_id=bytes.fromhex(r["traceId"]),
            span_id=bytes.fromhex(r["spanId"]),
            parent_span_id=bytes.fromhex(r["parentSpanId"]) if r.get("parentSpanId") else b"",
            name=r["spanName"],
            kind=KINDS.get(r.get("spanKind", ""), Span.SPAN_KIND_INTERNAL),
            start_time_unix_nano=start,
            end_time_unix_nano=start + int(r.get("durationNs", 0)),
            status=Status(code=STATUS.get(r.get("statusCode", "Unset"), 0), message=r.get("statusMessage") or ""),
        )
        for k, v in (r.get("spanAttributes") or {}).items():
            if drop_content and k in CONTENT_KEYS:
                continue
            span.attributes.append(KeyValue(key=k, value=_val(v)))
        scope.spans.append(span)
    rs = ResourceSpans(resource=Resource(attributes=[KeyValue(key=k, value=_val(v)) for k, v in attrs.items()]))
    rs.scope_spans.extend(by_scope.values())
    return ExportTraceServiceRequest(resource_spans=[rs])


def main() -> int:
    from post_batch import auth_headers, post_http

    ap = argparse.ArgumentParser()
    ap.add_argument("spans_json")
    ap.add_argument("--url", required=True)
    ap.add_argument("--auth", default="headers")
    ap.add_argument("--resource", action="append", default=[])
    ap.add_argument("--trace-id", action="append", default=[])
    ap.add_argument("--drop-content", action="store_true")
    a = ap.parse_args()
    rows = json.load(open(a.spans_json))["data"]
    req = build_request(rows, trace_ids=a.trace_id or None, resource=dict(r.split("=", 1) for r in a.resource),
                        drop_content=a.drop_content)
    n = sum(len(s.spans) for s in req.resource_spans[0].scope_spans)
    status, body = post_http(a.url, req, encoding="proto", headers=auth_headers(a.auth), gzip_body=False)
    print(f"status={status} spans={n} body={body[:120]!r}")
    return 0 if str(status) == "200" else 1


if __name__ == "__main__":
    sys.exit(main())
