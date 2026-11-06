#!/usr/bin/env python3
"""STAND-IN for the Cloudflare AI Gateway OpenTelemetry exporter (the sending side only).

For trying the collector without a Cloudflare account. No Cloudflare code or account is involved. This script
posts the span shape a real gateway exported on 2026-10-18 (see gateway_fixture.py; `--doc-names` posts the
attribute names on Cloudflare's page instead), from your machine, with the exporter's own knobs:

  --headers      the exporter's Headers field: a JSON object ({"Authorization": "Bearer <token>"})
  --header N=V   one header, value read from environment variable V (keeps keys out of shell history)
  --content-type json (Cloudflare's default) or protobuf
  --gzip         gzip the body (the real gateway sent plain bodies; the collector accepts both)

  standin_cloudflare.py send --endpoint http://localhost:4318/v1/traces \\
      --header Authorization=EXPORT_AUTH --scenario success --live

`--live` first makes a real call through an OpenAI-compatible endpoint (STANDIN_UPSTREAM_BASE_URL,
STANDIN_UPSTREAM_API_KEY, STANDIN_MODEL; CLIPROXY_* in the TH-8103 setup), so the prompt, completion and
token counts are real model output. The wrapping into a Cloudflare span is still synthetic.

Prints one JSON line per request (HTTP status, trace id, scenario). Never prints header values.
Exit status 0 when every request got a 2xx, 1 otherwise.
"""
from __future__ import annotations

import argparse
import gzip
import http.client
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gateway_fixture as gf  # noqa: E402


def parse_headers(headers_json: str | None, header_env: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    if headers_json:
        data = json.loads(headers_json)
        if not isinstance(data, dict):
            raise SystemExit("--headers must be a JSON object")
        headers.update({str(k): str(v) for k, v in data.items()})
    for item in header_env:
        name, _, var = item.partition("=")
        if not name or not var or var not in os.environ:
            raise SystemExit(f"--header {item!r}: use NAME=ENVVAR and export ENVVAR")
        headers[name] = os.environ[var]
    return headers


def post(endpoint: str, body: dict, headers: dict[str, str], *, content_type: str = "json", gzip_body: bool = False) -> tuple[int, str]:
    if content_type == "protobuf":
        raw, ctype = gf.to_protobuf(body), "application/x-protobuf"
    else:
        raw, ctype = json.dumps(body).encode(), "application/json"
    h = {"Content-Type": ctype, "User-Agent": "cloudflare-ai-gateway-standin/1"}
    h.update(headers)
    if gzip_body:
        raw = gzip.compress(raw)
        h["Content-Encoding"] = "gzip"
    req = urllib.request.Request(endpoint, data=raw, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        return 0, f"connection error: {exc.reason}"
    except (http.client.HTTPException, OSError) as exc:
        return 0, f"connection error: {type(exc).__name__}"


def chat(messages: list[dict]) -> dict:
    base = os.environ.get("STANDIN_UPSTREAM_BASE_URL") or os.environ.get("CLIPROXY_OPENAI_BASE_URL")
    key = os.environ.get("STANDIN_UPSTREAM_API_KEY") or os.environ.get("CLIPROXY_API_KEY")
    if not base or not key:
        raise SystemExit("--live needs STANDIN_UPSTREAM_BASE_URL and STANDIN_UPSTREAM_API_KEY (or CLIPROXY_*)")
    model = os.environ.get("STANDIN_MODEL", "gpt-6-luna")
    body = {"model": model, "messages": messages, "max_completion_tokens": 300}
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def scenario_request(a: argparse.Namespace) -> gf.GatewayRequest:
    marker = a.marker or gf.env_marker()
    meta = {"team": "engineering", "feature": a.meta_marker or "support-bot"}
    prompt = [{"role": "user", "content": f"Order {marker} has this customer note: {marker}-note. In one short sentence, what should support do?"}]
    r = gf.GatewayRequest(prompt=prompt, metadata=meta, big_chars=a.big_chars, doc_names=a.doc_names,
                          otel_trace_id=a.otel_trace_id, otel_parent_span_id=a.otel_parent_span_id)
    if a.live:
        resp = chat(prompt)
        usage = resp.get("usage") or {}
        r.model = os.environ.get("STANDIN_MODEL", "gpt-6-luna")
        r.completion = resp["choices"][0]["message"]
        r.input_tokens, r.output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    else:
        r.completion = {"role": "assistant", "content": f"Order {marker} shipped with ACME."}
    if a.scenario == "error":
        r.error_message = f"Provider returned 429 for {marker}: rate limit for user {marker.lower()}@example.test"
        r.exception_event = a.exception_event
        r.completion, r.output_tokens = None, None
    elif a.scenario == "no-usage":
        r.input_tokens = r.output_tokens = None
    elif a.scenario == "no-prompt":
        r.prompt = None
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("caller", help="post the application's own parent span for a linked trace (not part of the exporter)")
    c.add_argument("--endpoint", required=True); c.add_argument("--headers"); c.add_argument("--header", action="append", default=[], metavar="NAME=ENVVAR")
    c.add_argument("--trace-id", required=True); c.add_argument("--span-id", required=True)
    c.add_argument("--resource", action="append", default=[], metavar="KEY=VALUE")
    p = sub.add_parser("send")
    p.add_argument("--endpoint", required=True, help="the exporter's URL field, path included")
    p.add_argument("--headers", help="the exporter's Headers field: a JSON object")
    p.add_argument("--header", action="append", default=[], metavar="NAME=ENVVAR")
    p.add_argument("--content-type", default="json", choices=["json", "protobuf"])
    p.add_argument("--gzip", action="store_true")
    p.add_argument("--scenario", default="success", choices=["success", "error", "no-usage", "no-prompt"],
                   help="error is SYNTHETIC: the real gateway exported no span for a failed request")
    p.add_argument("--doc-names", action="store_true", help="use the attribute names on Cloudflare's page")
    p.add_argument("--live", action="store_true", help="real model call through STANDIN_UPSTREAM_* / CLIPROXY_* first")
    p.add_argument("--marker", help="unique string placed in the prompt, the completion and (error scenario) the error text")
    p.add_argument("--meta-marker", help="value of the custom metadata key `feature` (metadata is not content-gated)")
    p.add_argument("--resource", action="append", default=[], metavar="KEY=VALUE", help="extra resource attribute, for example project_name=...")
    p.add_argument("--big-chars", type=int, default=0)
    p.add_argument("--exception-event", action="store_true", help="error scenario: add a SYNTHETIC exception event with a stack trace")
    p.add_argument("--otel-trace-id", help="what the caller sent in cf-aig-otel-trace-id (32 hex)")
    p.add_argument("--otel-parent-span-id", help="what the caller sent in cf-aig-otel-parent-span-id (16 hex)")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--out", help="append one JSON line per request here (no header values)")
    a = ap.parse_args()

    headers = parse_headers(a.headers, a.header)
    if a.cmd == "caller":
        status, resp = post(a.endpoint, gf.build_caller_request(a.trace_id, a.span_id, dict(i.split("=", 1) for i in a.resource)), headers)
        print(json.dumps({"cmd": "caller", "status": status, "trace_id": a.trace_id, "body": resp[:160] if status >= 300 else ""}))
        return 0 if 200 <= status < 300 else 1
    resource = dict(item.split("=", 1) for item in a.resource)
    r = scenario_request(a)
    body = gf.build_request(r, resource)
    trace_id = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    rc = 0
    for i in range(a.repeat):
        status, resp = post(a.endpoint, body, headers, content_type=a.content_type, gzip_body=a.gzip)
        line = {"cmd": "send", "scenario": a.scenario, "status": status, "trace_id": trace_id, "attempt": i + 1,
                "content_type": a.content_type, "model": r.model, "tokens": [r.input_tokens, r.output_tokens],
                "body": resp[:160] if status >= 300 or status == 0 else ""}
        print(json.dumps(line))
        if a.out:
            with open(a.out, "a") as f:
                f.write(json.dumps(line) + "\n")
        if not 200 <= status < 300:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
