#!/usr/bin/env python3
"""OTLP/JSON requests shaped like OpenRouter Broadcast's OpenTelemetry Collector destination.

STAND-IN. Nothing here was captured from OpenRouter. The request body is built from the attribute
keys OpenRouter publishes (retrieved 2026-10-15):

  https://openrouter.ai/docs/guides/features/broadcast
  https://openrouter.ai/docs/guides/features/broadcast/otel-collector
  https://openrouter.ai/docs/guides/features/broadcast/webhook      (payload example, Test Connection)
  https://openrouter.ai/docs/guides/features/broadcast/grafana      (resource and span attribute list)
  https://openrouter.ai/docs/guides/features/broadcast/elastic      (resource and span attribute list)

Only keys that appear on those pages are used. Where the pages leave something open, the choice made
here is marked ASSUMED, and the page in this repo says the same:

  * the span tree: a root span, an optional `span_name` span, and a generation span under it
  * the shape of the values of span.input / span.output / gen_ai.prompt / gen_ai.completion
    (a JSON string of the messages is used)
  * how a failed request is expressed in OTLP (the status code and message of the generation span)
  * span kinds, instrumentation scope name, span ids, and which of the two token-key spellings the
    real exporter writes (see TOKEN_KEYS)

The cost attribute key is NOT published, so no cost attribute is written.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

# The Webhook page example writes gen_ai.usage.prompt_tokens / completion_tokens. The Grafana, Elastic
# and OpenTelemetry Collector pages write gen_ai.usage.input_tokens / output_tokens / total_tokens.
TOKEN_KEYS = {
    "current": ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.usage.total_tokens"),
    "legacy": ("gen_ai.usage.prompt_tokens", "gen_ai.usage.completion_tokens", None),
}

STATUS_UNSET, STATUS_OK, STATUS_ERROR = 0, 1, 2
KIND_INTERNAL, KIND_CLIENT = 1, 3


def kv(key: str, value: Any) -> dict:
    """One OTLP/JSON KeyValue. 64-bit integers are strings in OTLP/JSON, as in OpenRouter's own example."""
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}
    elif isinstance(value, float):
        v = {"doubleValue": value}
    else:
        v = {"stringValue": str(value)}
    return {"key": key, "value": v}


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


@dataclass
class Generation:
    """One OpenRouter request, as Broadcast would report it."""

    model: str = "openai/gpt-4o-mini"            # the slug the caller asked for
    response_model: str | None = None             # defaults to `model`
    provider: str = "openai"                      # gen_ai.system
    prompt: list[dict] = field(default_factory=lambda: [{"role": "user", "content": "Hello!"}])
    completion: dict | None = field(default_factory=lambda: {"role": "assistant", "content": "Hi there."})
    input_tokens: int | None = 9
    output_tokens: int | None = 4
    finish_reason: str | None = "stop"
    response_id: str | None = None
    user: str | None = "user_12345"               # request field `user`      -> user.id
    session_id: str | None = "session_abc"        # request field `session_id` -> session.id
    metadata: dict[str, Any] = field(default_factory=lambda: {"environment": "staging"})  # `trace` -> trace.metadata.*
    trace_name: str | None = None                 # root span name; defaults to the model slug
    span_name: str | None = None                  # optional intermediate span
    generation_name: str | None = None            # generation span name; defaults to the model slug
    trace_id: str | None = None                   # 32 hex chars
    parent_span_id: str | None = None             # 16 hex chars, a span of the caller's own trace
    error_message: str | None = None              # ASSUMED: expressed as OTLP status ERROR + message
    exception_event: bool = False                 # SYNTHETIC: an OTel `exception` span event. OpenRouter does not
                                                  # document one; it exercises the recipe's defensive rule.
    privacy_mode: bool = False                    # the destination's Privacy Mode checkbox
    token_style: str = "current"                  # "current" | "legacy" (see TOKEN_KEYS)
    cost_metadata: bool = False                   # the destination's "Cost" generation-metadata opt-in
    inter_token_latency_ms: float | None = 12.5
    latency_ms: int = 900
    big_chars: int = 0                            # pad span.input to this many characters
    start_ns: int | None = None


def _content_attrs(g: Generation) -> list[dict]:
    """Prompt and completion, once per generation, on the generation span (Privacy Mode drops them)."""
    if g.privacy_mode:
        return []
    out: list[dict] = []
    if g.prompt is not None:
        text = json.dumps(g.prompt, ensure_ascii=False)
        if g.big_chars:
            text = text + " " + "x" * g.big_chars
        out += [kv("span.input", text), kv("gen_ai.prompt", text)]
    if g.completion is not None:
        text = json.dumps(g.completion, ensure_ascii=False)
        out += [kv("span.output", text), kv("gen_ai.completion", text)]
    return out


def _generation_metadata(g: Generation) -> list[tuple[str, Any]]:
    """`openrouter_generation.*` fields. Only documented keys. Present with the destination's Cost opt-in."""
    if not g.cost_metadata:
        return []
    pairs: list[tuple[str, Any]] = [
        ("cache_write_tokens", 0),
        ("usage_is_estimated", False),
    ]
    if g.privacy_mode:
        pairs += [("upstream_raw_response_usage", "null"), ("upstream_raw_response_usage_suppression_reason", "privacy_mode")]
    else:
        pairs += [
            ("upstream_raw_response_usage",
             json.dumps({"input_tokens": g.input_tokens, "output_tokens": g.output_tokens}, separators=(",", ":")))
        ]
    return pairs


def build_spans(g: Generation) -> tuple[str, list[dict]]:
    trace_id = g.trace_id or new_trace_id()
    end = g.start_ns + g.latency_ms * 1_000_000 if g.start_ns else time.time_ns()
    start = g.start_ns or end - g.latency_ms * 1_000_000
    root_id, gen_id = new_span_id(), new_span_id()
    mid_id = new_span_id() if g.span_name else None

    user_session = []
    if g.user:
        user_session.append(kv("user.id", g.user))
    if g.session_id:
        user_session.append(kv("session.id", g.session_id))
    meta = [kv(f"trace.metadata.{k}", v) for k, v in g.metadata.items()]
    gen_meta = _generation_metadata(g)

    root_attrs = user_session + meta + [kv(f"trace.metadata.openrouter_generation.{k}", v) for k, v in gen_meta]
    root = {
        "traceId": trace_id,
        "spanId": root_id,
        "name": g.trace_name or g.model,
        "kind": KIND_INTERNAL,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "attributes": root_attrs,
        "status": {"code": STATUS_UNSET},
    }
    if g.parent_span_id:
        root["parentSpanId"] = g.parent_span_id

    in_key, out_key, total_key = TOKEN_KEYS[g.token_style]
    a: list[dict] = [kv("gen_ai.operation.name", "chat"), kv("gen_ai.system", g.provider), kv("gen_ai.request.model", g.model)]
    if not g.error_message:
        a.append(kv("gen_ai.response.model", g.response_model or g.model))
        a.append(kv("gen_ai.response.id", g.response_id or f"gen-{int(time.time())}-{secrets.token_hex(8)}"))
        if g.finish_reason:
            a.append(kv("gen_ai.response.finish_reason", g.finish_reason))
    if g.input_tokens is not None:
        a.append(kv(in_key, g.input_tokens))
    if g.output_tokens is not None:
        a.append(kv(out_key, g.output_tokens))
    if total_key and g.input_tokens is not None and g.output_tokens is not None:
        a.append(kv(total_key, g.input_tokens + g.output_tokens))
    if g.inter_token_latency_ms is not None and not g.error_message:
        a.append(kv("openrouter.inter_token_latency_ms", g.inter_token_latency_ms))
    a += _content_attrs(g) + user_session + meta
    a += [kv(f"span.metadata.openrouter_generation.{k}", v) for k, v in gen_meta]
    gen = {
        "traceId": trace_id,
        "spanId": gen_id,
        "parentSpanId": mid_id or root_id,
        "name": g.generation_name or g.model,
        "kind": KIND_CLIENT,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "attributes": a,
        "status": {"code": STATUS_ERROR, "message": g.error_message} if g.error_message else {"code": STATUS_UNSET},
    }
    if g.error_message and g.exception_event:
        gen["events"] = [{
            "timeUnixNano": str(end),
            "name": "exception",
            "attributes": [
                kv("exception.type", "ProviderError"),
                kv("exception.message", g.error_message),
                kv("exception.stacktrace", "Traceback (most recent call last):\n  File \"/srv/orb-gateway/handler.py\", line 88, in run\n"
                   f"ProviderError: {g.error_message}"),
            ],
        }]
    spans = [root]
    if mid_id:
        spans.append({
            "traceId": trace_id, "spanId": mid_id, "parentSpanId": root_id, "name": g.span_name, "kind": KIND_INTERNAL,
            "startTimeUnixNano": str(start), "endTimeUnixNano": str(end), "attributes": [], "status": {"code": STATUS_UNSET},
        })
    spans.append(gen)
    return trace_id, spans


def build_request(g: Generation, resource: dict[str, str] | None = None) -> dict:
    """The JSON body of one Broadcast POST. `resource` adds resource attributes (for example project_name)
    to stand in for a stamp; OpenRouter itself sends none besides the three below."""
    trace_id, spans = build_spans(g)
    res = [kv("service.name", "openrouter"), kv("service.version", "1.0.0"), kv("openrouter.trace.id", trace_id)]
    res += [kv(k, v) for k, v in (resource or {}).items()]
    return {
        "resourceSpans": [{
            "resource": {"attributes": res},
            "scopeSpans": [{"scope": {"name": "openrouter"}, "spans": spans}],
        }]
    }


def test_connection_request() -> dict:
    """Test Connection: the Webhook page says OpenRouter sends an empty OTLP payload with
    `X-Test-Connection: true` and accepts 2xx or 400. The OpenTelemetry Collector page only says
    "Click Test Connection". ASSUMED to behave the same."""
    return {"resourceSpans": []}


def attr_dict(span: dict) -> dict:
    """Flatten a span's attributes for assertions."""
    out = {}
    for item in span.get("attributes", []):
        (kind, val), = item["value"].items()
        out[item["key"]] = int(val) if kind == "intValue" else val
    return out


def env_marker(prefix: str = "ORB") -> str:
    return f"{prefix}{secrets.token_hex(5).upper()}"


if __name__ == "__main__":
    print(json.dumps(build_request(Generation(), {"project_name": os.environ.get("FI_PROJECT_NAME", "my-openrouter")}), indent=2))
