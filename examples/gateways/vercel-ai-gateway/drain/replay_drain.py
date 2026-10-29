#!/usr/bin/env python3
"""Replay a Vercel AI Gateway Trace Drain shaped OTLP trace into an OTLP/HTTP collector.

This is a fixture replay, NOT a Vercel drain. No Vercel account, plan or fee is
involved. The fixture (drain-shaped-trace.otlp.json) uses the span and attribute
names Vercel publishes at
https://vercel.com/docs/ai-gateway/observability-and-spend/trace-drains
with placeholder values, the two fixed resource attributes
(service.name=ai-gateway, service.namespace=vercel) and no prompt or
completion content, as Vercel states.

The drain form cannot set resource attributes, so the first run below mimics a
drain exactly: no project_name. The second adds the attribute a drain cannot
add, to show the difference.

  replay_drain.py --endpoint http://localhost:4318/v1/traces                      # as a drain sends it
  replay_drain.py --endpoint http://localhost:4318/v1/traces --project-name demo  # what a drain cannot do

Auth is the Future AGI key pair in the X-Api-Key / X-Secret-Key headers
(FI_API_KEY / FI_SECRET_KEY), which the drain form can send as custom headers.
"--auth bearer" shows that a Bearer token is refused.
Exit code 0 when the collector answers 2xx, 1 otherwise.
"""
import argparse
import base64
import copy
import gzip
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURE = HERE / "drain-shaped-trace.otlp.json"
KIND_NAMES = {1: "SPAN_KIND_INTERNAL", 2: "SPAN_KIND_SERVER", 3: "SPAN_KIND_CLIENT"}
KIND_DOC_EXAMPLE = {1: "internal", 2: "server", 3: "client"}


def load_fixture(path=DEFAULT_FIXTURE):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def with_project_name(payload, project_name, project_type=None):
    """Return a copy whose resources carry project_name (and project_type). A drain cannot do this."""
    out = copy.deepcopy(payload)
    for rs in out["resourceSpans"]:
        attrs = rs.setdefault("resource", {}).setdefault("attributes", [])
        attrs.append({"key": "project_name", "value": {"stringValue": project_name}})
        if project_type:
            attrs.append({"key": "project_type", "value": {"stringValue": project_type}})
    return out


def fresh_ids(payload, now_ns=None):
    """Give the trace new ids and move it to 'now', so every replay is a new trace."""
    out = copy.deepcopy(payload)
    now_ns = now_ns or time.time_ns()
    trace = secrets.token_hex(16)
    spans = [sp for rs in out["resourceSpans"] for ss in rs["scopeSpans"] for sp in ss["spans"]]
    ids = {sp["spanId"]: secrets.token_hex(8) for sp in spans}
    first = min(int(sp["startTimeUnixNano"]) for sp in spans)
    shift = (now_ns - 2_000_000_000) - first
    for sp in spans:
        sp["traceId"] = trace
        sp["spanId"] = ids[sp["spanId"]]
        if sp.get("parentSpanId"):
            sp["parentSpanId"] = ids[sp["parentSpanId"]]
        sp["startTimeUnixNano"] = str(int(sp["startTimeUnixNano"]) + shift)
        sp["endTimeUnixNano"] = str(int(sp["endTimeUnixNano"]) + shift)
    return out


def set_kind_style(payload, style):
    out = copy.deepcopy(payload)
    if style == "int":
        return out
    table = KIND_NAMES if style == "enum" else KIND_DOC_EXAMPLE
    for rs in out["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for sp in ss["spans"]:
                sp["kind"] = table[sp["kind"]]
    return out


def encode(payload, fmt):
    """OTLP/HTTP body and content type, in the two formats the drain form offers."""
    if fmt == "json":
        return json.dumps(payload).encode(), "application/json"
    from google.protobuf.json_format import Parse
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

    msg = Parse(json.dumps(_ids_hex_to_base64(payload)), trace_service_pb2.ExportTraceServiceRequest())
    return msg.SerializeToString(), "application/x-protobuf"


def _ids_hex_to_base64(payload):
    """OTLP/JSON writes trace and span ids as hex; protobuf's own JSON mapping expects base64."""
    out = copy.deepcopy(payload)
    for rs in out["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for sp in ss["spans"]:
                for key in ("traceId", "spanId", "parentSpanId"):
                    if sp.get(key):
                        sp[key] = base64.b64encode(bytes.fromhex(sp[key])).decode()
    return out


def post(endpoint, body, content_type, headers=None, timeout=20):
    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def auth_headers(mode, api_key, secret_key):
    if mode == "keys":
        return {"X-Api-Key": api_key, "X-Secret-Key": secret_key}
    if mode == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    return {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", default=os.environ.get("FI_BASE_URL", "http://localhost:4318").rstrip("/") + "/v1/traces")
    ap.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    ap.add_argument("--format", choices=["json", "protobuf"], default="json")
    ap.add_argument("--project-name", default=None, help="add resource attribute project_name (a drain cannot)")
    ap.add_argument("--project-type", default=None)
    ap.add_argument("--auth", choices=["keys", "bearer", "none"], default="keys")
    ap.add_argument("--kind-style", choices=["int", "enum", "doc-example"], default="int",
                    help="how span kind is written in JSON; doc-example copies Vercel's reference page ('server')")
    ap.add_argument("--gzip", action="store_true", help="gzip the body (the collector refuses gzip)")
    ap.add_argument("--keep-ids", action="store_true", help="do not generate new trace/span ids")
    a = ap.parse_args(argv)

    payload = load_fixture(a.fixture)
    if not a.keep_ids:
        payload = fresh_ids(payload)
    if a.project_name:
        payload = with_project_name(payload, a.project_name, a.project_type)
    if a.format == "json":
        payload = set_kind_style(payload, a.kind_style)
    body, ctype = encode(payload, a.format)
    headers = auth_headers(a.auth, os.environ.get("FI_API_KEY", ""), os.environ.get("FI_SECRET_KEY", ""))
    if a.gzip:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    trace = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    status, text = post(a.endpoint, body, ctype, headers)
    print(f"POST {a.endpoint} format={a.format} auth={a.auth} project_name={a.project_name or '(none)'} trace_id={trace}")
    printable = "".join(ch for ch in text[:400] if ch.isprintable() or ch in "\n\t")
    print(f"HTTP {status} {printable.strip()}")
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
