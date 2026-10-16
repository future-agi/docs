#!/usr/bin/env python3
"""OTLP requests shaped like the Cloudflare AI Gateway OpenTelemetry exporter.

STAND-IN. Nothing here was captured from Cloudflare. The span carries the attributes Cloudflare
documents (https://developers.cloudflare.com/ai-gateway/observability/otel-integration/, page
"Last updated Sep 24, 2026", read 2026-10-16):

  gen_ai.request.model        string
  gen_ai.model.provider       string   (Cloudflare's name; NOT gen_ai.provider.name)
  gen_ai.usage.input_tokens   int
  gen_ai.usage.output_tokens  int
  gen_ai.prompt_json          string   JSON-encoded prompt/messages
  gen_ai.completion_json      string   JSON-encoded completion
  gen_ai.usage.cost           double   estimated cost
  <key>                       custom metadata from the `cf-aig-metadata` request header, one attribute per
                              key (keys starting with `gen_ai.` are dropped by Cloudflare)

Trace linking follows the same page: `cf-aig-otel-trace-id` (32 hex) is used as the trace id and
`cf-aig-otel-parent-span-id` (16 hex) as the parent span id.

Where the page is silent the choice made here is marked ASSUMED, and the docs page says the same:
  * span name, span kind, instrumentation scope and resource attributes (one span per gateway request)
  * the exact JSON shape of gen_ai.prompt_json / gen_ai.completion_json
  * how a failed request is expressed (status ERROR plus message)
  * the value of gen_ai.usage.cost (SYNTHETIC here: tokens times a made-up rate)
"""
from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

STATUS_UNSET, STATUS_OK, STATUS_ERROR = 0, 1, 2
KIND_CLIENT = 3
TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
COST_PER_1K_TOKENS = 0.0005     # SYNTHETIC


def kv(key: str, value: Any) -> dict:
    """One OTLP/JSON KeyValue. 64-bit integers are strings in OTLP/JSON."""
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}
    elif isinstance(value, float):
        v = {"doubleValue": value}
    else:
        v = {"stringValue": str(value)}
    return {"key": key, "value": v}


@dataclass
class GatewayRequest:
    """One request through the gateway, as the exporter would report it."""

    model: str = "gpt-4o-mini"
    provider: str = "openai"
    prompt: list[dict] | None = field(default_factory=lambda: [{"role": "user", "content": "Hello!"}])
    completion: dict | None = field(default_factory=lambda: {"role": "assistant", "content": "Hi there."})
    input_tokens: int | None = 9
    output_tokens: int | None = 4
    cost: float | None = None                     # None: computed from the tokens (SYNTHETIC)
    metadata: dict[str, Any] = field(default_factory=lambda: {"team": "engineering"})  # cf-aig-metadata
    otel_trace_id: str | None = None              # cf-aig-otel-trace-id
    otel_parent_span_id: str | None = None        # cf-aig-otel-parent-span-id
    error_message: str | None = None              # ASSUMED: status ERROR + message
    exception_event: bool = False                 # SYNTHETIC: an OTel exception event, to exercise the privacy rule
    latency_ms: int = 900
    big_chars: int = 0


def sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Cloudflare: custom metadata keys that start with `gen_ai.` are not added."""
    return {k: v for k, v in meta.items() if not str(k).startswith("gen_ai.")}


def build_span(r: GatewayRequest) -> dict:
    if r.otel_trace_id is not None and not TRACE_ID_RE.match(r.otel_trace_id):
        raise ValueError("cf-aig-otel-trace-id must be 32 lowercase hex characters")
    if r.otel_parent_span_id is not None and not SPAN_ID_RE.match(r.otel_parent_span_id):
        raise ValueError("cf-aig-otel-parent-span-id must be 16 lowercase hex characters")
    end = time.time_ns()
    start = end - r.latency_ms * 1_000_000
    a: list[dict] = [kv("gen_ai.request.model", r.model), kv("gen_ai.model.provider", r.provider)]
    if r.input_tokens is not None:
        a.append(kv("gen_ai.usage.input_tokens", r.input_tokens))
    if r.output_tokens is not None:
        a.append(kv("gen_ai.usage.output_tokens", r.output_tokens))
    if r.prompt is not None:
        text = json.dumps(r.prompt, ensure_ascii=False)
        if r.big_chars:
            text += " " + "x" * r.big_chars
        a.append(kv("gen_ai.prompt_json", text))
    if r.completion is not None:
        a.append(kv("gen_ai.completion_json", json.dumps(r.completion, ensure_ascii=False)))
    cost = r.cost
    if cost is None and r.input_tokens is not None and r.output_tokens is not None:
        cost = round((r.input_tokens + r.output_tokens) / 1000 * COST_PER_1K_TOKENS, 8)
    if cost is not None:
        a.append(kv("gen_ai.usage.cost", float(cost)))
    a += [kv(k, v) for k, v in sanitize_metadata(r.metadata).items()]
    span = {
        "traceId": r.otel_trace_id or secrets.token_hex(16),
        "spanId": secrets.token_hex(8),
        "name": "ai-gateway.request",                      # ASSUMED
        "kind": KIND_CLIENT,                               # ASSUMED
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "attributes": a,
        "status": {"code": STATUS_ERROR, "message": r.error_message} if r.error_message else {"code": STATUS_UNSET},
    }
    if r.otel_parent_span_id:
        span["parentSpanId"] = r.otel_parent_span_id
    if r.error_message and r.exception_event:
        span["events"] = [{
            "timeUnixNano": str(end), "name": "exception",
            "attributes": [
                kv("exception.type", "ProviderError"),
                kv("exception.message", r.error_message),
                kv("exception.stacktrace", "Traceback (most recent call last):\n  File \"/srv/cf-gateway/handler.py\", line 88, in run\n"
                   f"ProviderError: {r.error_message}"),
            ],
        }]
    return span


def build_request(r: GatewayRequest, resource: dict[str, str] | None = None) -> dict:
    """The JSON body of one export. `resource` adds resource attributes (for example project_name) to stand in for a stamp;
    the exporter itself has no field for them."""
    res = [kv("service.name", "cloudflare-ai-gateway")]           # ASSUMED
    res += [kv(k, v) for k, v in (resource or {}).items()]
    return {"resourceSpans": [{
        "resource": {"attributes": res},
        "scopeSpans": [{"scope": {"name": "cloudflare-ai-gateway"}, "spans": [build_span(r)]}],   # ASSUMED scope
    }]}


def build_caller_request(trace_id: str, span_id: str, resource: dict[str, str], name: str = "support-request") -> dict:
    """The application's own span, the parent of a gateway span that was linked with the cf-aig-otel-* headers.
    In real use your instrumented app sends this (for example with traceAI); it is here so a linked trace is whole."""
    end = time.time_ns()
    span = {
        "traceId": trace_id, "spanId": span_id, "name": name, "kind": 2,
        "startTimeUnixNano": str(end - 1_500_000_000), "endTimeUnixNano": str(end),
        "attributes": [kv("fi.span.kind", "CHAIN")], "status": {"code": STATUS_UNSET},
    }
    res = [kv("service.name", "my-app")] + [kv(k, v) for k, v in resource.items()]
    return {"resourceSpans": [{"resource": {"attributes": res},
                               "scopeSpans": [{"scope": {"name": "my-app"}, "spans": [span]}]}]}


def to_protobuf(body: dict) -> bytes:
    """The same request as OTLP/protobuf (Cloudflare's other content type)."""
    import base64
    import copy
    from google.protobuf.json_format import ParseDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    body = copy.deepcopy(body)
    # OTLP/JSON writes ids as hex; the protobuf JSON mapping wants base64 for bytes fields.
    for rs in body.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for sp in ss.get("spans", []):
                for k in ("traceId", "spanId", "parentSpanId"):
                    if k in sp:
                        sp[k] = base64.b64encode(bytes.fromhex(sp[k])).decode()
    return ParseDict(body, ExportTraceServiceRequest()).SerializeToString()


def attr_dict(span: dict) -> dict:
    out = {}
    for item in span.get("attributes", []):
        (kind, val), = item["value"].items()
        out[item["key"]] = int(val) if kind == "intValue" else val
    return out


def env_marker(prefix: str = "CFG") -> str:
    return f"{prefix}{secrets.token_hex(5).upper()}"


if __name__ == "__main__":
    print(json.dumps(build_request(GatewayRequest(), {"project_name": "my-cloudflare-gateway"}), indent=2))
