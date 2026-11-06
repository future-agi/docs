#!/usr/bin/env python3
"""SYNTHETIC OTLP/HTTP trace body shaped like what Microsoft says the Azure AI Gateway tier emits. Not captured from Azure.

Nobody ran a real AI Gateway tier instance for this recipe (it needs an Azure subscription and is billed, in
preview, in two regions). What Microsoft publishes about the trace, and so what this builder follows:
  * a root span per gateway request, plus child spans for policy execution with "policy type, outcome, and
    latency" (release notes 2026-08-28)
  * attributes that follow the OpenTelemetry generative AI conventions "where applicable, including model,
    operation, tool, and MCP method attributes", plus API key attribution (2026-08-28)
  * JWT claims as `azure.ai_gateway.identity.claims.<claim>` (tid, oid, appid, azp ...) (2026-09-24)
What is INVENTED here, to give the pipeline something to chew on, and must not be read as Azure's schema:
  every attribute name that is not `gen_ai.*` or `azure.ai_gateway.identity.claims.*` (policy type/outcome, API
  key attribution, cost), the span names, the span kinds, and the presence of prompt / completion text
  (`--with-content`, to prove the content filter; Microsoft does not say whether the trace ever carries it).

Usage
  gateway_trace.py --url http://127.0.0.1:14298/v1/traces --header "Authorization=Bearer T" [--project-name P]
                   [--marker TEXT] [--with-content] [--compression gzip|none] [--scenario ok|blocked|both]
Prints one line per POST: HTTP status and the trace ids. Never prints header values.
"""
import argparse
import gzip
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as svc
from opentelemetry.proto.common.v1 import common_pb2 as common
from opentelemetry.proto.resource.v1 import resource_pb2 as resource
from opentelemetry.proto.trace.v1 import trace_pb2 as trace


def kv(key, value):
    v = common.AnyValue()
    if isinstance(value, bool):
        v.bool_value = value
    elif isinstance(value, int):
        v.int_value = value
    elif isinstance(value, float):
        v.double_value = value
    else:
        v.string_value = str(value)
    return common.KeyValue(key=key, value=v)


def span(trace_id, parent, name, kind, start, dur_ms, attrs, error=None, events=()):
    s = trace.Span(
        trace_id=trace_id, span_id=secrets.token_bytes(8), name=name, kind=kind,
        start_time_unix_nano=start, end_time_unix_nano=start + int(dur_ms * 1e6),
    )
    if parent:
        s.parent_span_id = parent
    s.attributes.extend(kv(k, v) for k, v in attrs.items())
    if error:
        s.status.code = trace.Status.STATUS_CODE_ERROR
        s.status.message = error
    for ev_name, ev_attrs in events:
        e = s.events.add()
        e.name, e.time_unix_nano = ev_name, start + int(dur_ms * 1e6)
        e.attributes.extend(kv(k, v) for k, v in ev_attrs.items())
    return s


def build(scenario="ok", project_name=None, marker="", with_content=False):
    """Returns (ExportTraceServiceRequest, trace_id_hex)."""
    tid = secrets.token_bytes(16)
    now = time.time_ns() - 3_000_000_000
    res = {"service.name": "azure-ai-gateway", "cloud.provider": "azure"}
    if project_name:
        res["project_name"] = project_name
    chat = {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gpt-example-alias",
        "gen_ai.response.model": "gpt-example-2026-09",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.usage.input_tokens": 118,
        "gen_ai.usage.output_tokens": 42,
    }
    claims = {  # the "recommended preset": tid and oid on traces (clients appid/azp too, per 2026-09-24)
        "azure.ai_gateway.identity.claims.tid": "00000000-0000-0000-0000-00000000aaaa",
        "azure.ai_gateway.identity.claims.oid": "00000000-0000-0000-0000-00000000bbbb",
        "azure.ai_gateway.identity.claims.appid": "00000000-0000-0000-0000-00000000cccc",
    }
    blocked = scenario == "blocked"
    root_attrs = {
        "http.request.method": "POST", "url.path": "/models/openai/v1/chat/completions",
        "http.response.status_code": 429 if blocked else 200,
        "azure.ai_gateway.api_key.name": "team-a-prod",              # INVENTED name
        **claims, "gen_ai.operation.name": "chat", "gen_ai.request.model": chat["gen_ai.request.model"],
    }
    if with_content:
        root_attrs["gen_ai.input.messages"] = f'[{{"role":"user","content":"find {marker}"}}]'  # INVENTED presence
    spans = []
    root = span(tid, None, "POST /models/openai/v1/chat/completions", trace.Span.SPAN_KIND_SERVER, now, 900, root_attrs,
                error="LlmCostQuotaExceeded: budget reached for key team-a-prod " + marker if blocked else None,
                events=[("exception", {"exception.type": "LlmCostQuotaExceeded",
                                       "exception.message": f"budget reached {marker}",
                                       "exception.stacktrace": f"Traceback (most recent call last): {marker}"})] if blocked else ())
    spans.append(root)
    spans.append(span(tid, root.span_id, "policy token-limit", trace.Span.SPAN_KIND_INTERNAL, now + 1_000_000, 2,
                      {"azure.ai_gateway.policy.type": "token-limit", "azure.ai_gateway.policy.outcome": "allowed"}))   # INVENTED
    spans.append(span(tid, root.span_id, "policy cost-limit", trace.Span.SPAN_KIND_INTERNAL, now + 4_000_000, 3,
                      {"azure.ai_gateway.policy.type": "cost-limit",
                       "azure.ai_gateway.policy.outcome": "blocked" if blocked else "allowed"},
                      error="LlmCostQuotaExceeded" if blocked else None))
    if not blocked:
        out = dict(chat)
        out["azure.ai_gateway.cost.estimated_usd"] = 0.0021                                                         # INVENTED
        if with_content:
            out["gen_ai.output.messages"] = f'[{{"role":"assistant","content":"found {marker}"}}]'                  # INVENTED presence
        spans.append(span(tid, root.span_id, "chat gpt-example-alias", trace.Span.SPAN_KIND_CLIENT, now + 8_000_000, 850, out))
    req = svc.ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.attributes.extend(kv(k, v) for k, v in res.items())
    ss = rs.scope_spans.add()
    ss.scope.name = "synthetic-azure-ai-gateway-shape"
    ss.spans.extend(spans)
    return req, tid.hex()


def post(url, req, headers, compression="none"):
    body = req.SerializeToString()
    h = {"Content-Type": "application/x-protobuf", **headers}
    if compression == "gzip":
        body, h["Content-Encoding"] = gzip.compress(body), "gzip"
    r = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--header", action="append", default=[], help="NAME=VALUE; a value starting with $ is read from that environment variable")
    ap.add_argument("--project-name")
    ap.add_argument("--marker", default="")
    ap.add_argument("--with-content", action="store_true")
    ap.add_argument("--compression", choices=["none", "gzip"], default="none")
    ap.add_argument("--scenario", choices=["ok", "blocked", "both"], default="ok")
    a = ap.parse_args(argv)
    headers = {}
    for h in a.header:
        k, _, v = h.partition("=")
        headers[k] = os.environ[v[1:]] if v.startswith("$") else v
    rc = 0
    for sc in (["ok", "blocked"] if a.scenario == "both" else [a.scenario]):
        req, tid = build(sc, a.project_name, a.marker, a.with_content)
        status = post(a.url, req, headers, a.compression)
        print(f"HTTP {status} scenario={sc} trace_id={tid} spans={len(req.resource_spans[0].scope_spans[0].spans)}")
        rc |= status != 200
    return rc


if __name__ == "__main__":
    sys.exit(main())
