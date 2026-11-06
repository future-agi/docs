#!/usr/bin/env python3
"""STAND-IN for OpenRouter Broadcast's OpenTelemetry Collector destination (the sender side only).

No OpenRouter code or account is involved. This script does what the destination's documentation says
the destination does, from your machine:

  probe   Test Connection: POST an empty OTLP/JSON payload (`{"resourceSpans": []}`) with
          `X-Test-Connection: true`. OpenRouter's Webhook page says 2xx or 400 pass; the OpenTelemetry
          Collector page only says "Click Test Connection", so the same rule is ASSUMED.
  send    POST one OTLP/JSON trace per generation, shaped from the attribute keys OpenRouter publishes
          (see broadcast_fixture.py). `--live` first makes a real call through an OpenAI-compatible
          endpoint (CLIProxy in the TH-8103 setup) so the prompt, completion, tool call and token counts
          are real model output. The wrapping into OpenRouter's span tree is still synthetic.

Headers are given the way the destination's Headers field takes them, as a JSON object, or one
`--header NAME=ENVVAR` at a time so keys stay out of the shell history:

  standin_openrouter.py probe --endpoint http://localhost:4318/v1/traces \\
      --headers '{"Authorization": "Bearer <token>"}'
  standin_openrouter.py send  --endpoint http://localhost:4318/v1/traces \\
      --header Authorization=BROADCAST_AUTH --scenario success --live

Prints one JSON line per request: HTTP status, trace id, scenario. Never prints header values.
Exit status 0 when every request was accepted (probe: by the 2xx-or-400 rule), 1 otherwise.
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
import broadcast_fixture as bf  # noqa: E402

SECRET_HEADERS = {"authorization", "x-api-key", "x-secret-key"}


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


def post(endpoint: str, body: dict, headers: dict[str, str], *, gzip_body: bool = False, test: bool = False) -> tuple[int, str]:
    raw = json.dumps(body).encode()
    h = {"Content-Type": "application/json", "User-Agent": "openrouter-broadcast-standin/1"}
    h.update(headers)
    if test:
        h["X-Test-Connection"] = "true"
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


def chat(messages: list[dict], tools: list[dict]) -> dict:
    base = os.environ.get("STANDIN_UPSTREAM_BASE_URL") or os.environ.get("CLIPROXY_OPENAI_BASE_URL")
    key = os.environ.get("STANDIN_UPSTREAM_API_KEY") or os.environ.get("CLIPROXY_API_KEY")
    if not base or not key:
        raise SystemExit("--live needs STANDIN_UPSTREAM_BASE_URL and STANDIN_UPSTREAM_API_KEY (or CLIPROXY_*)")
    model = os.environ.get("STANDIN_MODEL", "gpt-6-luna")
    body = {"model": model, "messages": messages, "tools": tools, "max_completion_tokens": 400}
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


ORDER_TOOL = [{
    "type": "function",
    "function": {
        "name": "get_order_status",
        "description": "Look up the shipping status of an order.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    },
}]


def live_generations(marker: str, note: str) -> list[bf.Generation]:
    """Two real model calls (tool call, then answer), each reported as its own OpenRouter generation."""
    model = os.environ.get("STANDIN_MODEL", "gpt-6-luna")
    slug = f"openai/{model}"
    messages = [{"role": "user", "content": f"Order {marker} has this customer note: {note}. What is its shipping status? Use the tool."}]
    first = chat(messages, ORDER_TOOL)
    m1 = first["choices"][0]["message"]
    gens = [_gen(slug, first, messages)]
    calls = m1.get("tool_calls") or []
    if calls:
        messages2 = messages + [m1] + [
            {"role": "tool", "tool_call_id": c["id"], "content": json.dumps({"status": "shipped", "carrier": "ACME", "ref": marker})}
            for c in calls
        ]
        second = chat(messages2, ORDER_TOOL)
        gens.append(_gen(slug, second, messages2))
    return gens


def _gen(slug: str, resp: dict, messages: list[dict]) -> bf.Generation:
    choice = resp["choices"][0]
    usage = resp.get("usage") or {}
    return bf.Generation(
        model=slug, response_model=slug, response_id=resp.get("id"),
        prompt=messages, completion=choice["message"], finish_reason=choice.get("finish_reason"),
        input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
    )


def scenario_generations(a: argparse.Namespace) -> list[bf.Generation]:
    marker = a.marker or bf.env_marker()
    note = f"{a.marker or marker}-note"
    if a.live:
        gens = live_generations(marker, note)
    else:
        gens = [bf.Generation(
            prompt=[{"role": "user", "content": f"Order {marker}: {note}. What is its shipping status?"}],
            completion={"role": "assistant", "content": f"Order {marker} shipped with ACME."},
        )]
    meta = {"environment": "staging", "feature": a.meta_marker or "support-bot"}
    for g in gens:
        g.metadata = dict(meta)
        g.session_id = a.session_id
        g.user = a.user
        g.cost_metadata = a.cost_metadata
        g.big_chars = a.big_chars
        if a.scenario == "privacy":
            g.privacy_mode = True
        elif a.scenario == "error":
            g.error_message = f"Provider returned 429 for {marker}: rate limit for user {marker.lower()}@example.test"
            g.exception_event = a.exception_event
            g.completion = None
            g.finish_reason = None
            g.output_tokens = None
        elif a.scenario == "legacy":
            g.token_style = "legacy"
        elif a.scenario == "nested":
            g.span_name = "Summarization Step"
            g.generation_name = "Generate Summary"
            g.trace_name = "Document Processing"
            g.trace_id = a.trace_id
            g.parent_span_id = a.parent_span_id
        elif a.scenario == "no-usage":
            g.input_tokens = g.output_tokens = None
    return gens


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("probe", "send"):
        p = sub.add_parser(name)
        p.add_argument("--endpoint", required=True, help="the destination's Endpoint field, path included")
        p.add_argument("--headers", help="the destination's Headers field: a JSON object")
        p.add_argument("--header", action="append", default=[], metavar="NAME=ENVVAR", help="take a header value from an environment variable")
        p.add_argument("--gzip", action="store_true", help="gzip the body (OpenRouter documents no compression either way)")
    s = sub.choices["send"]
    s.add_argument("--scenario", default="success", choices=["success", "privacy", "error", "nested", "legacy", "no-usage"])
    s.add_argument("--live", action="store_true", help="real model calls through STANDIN_UPSTREAM_* / CLIPROXY_* first")
    s.add_argument("--marker", help="unique string placed in the prompt, completion and (error scenario) the error text")
    s.add_argument("--meta-marker", help="value of trace.metadata.feature (custom metadata is not content-gated)")
    s.add_argument("--session-id", default="session_abc")
    s.add_argument("--user", default="user_12345")
    s.add_argument("--resource", action="append", default=[], metavar="KEY=VALUE", help="extra resource attribute, for example project_name=...")
    s.add_argument("--cost-metadata", action="store_true", help="include the openrouter_generation.* fields of the Cost opt-in")
    s.add_argument("--big-chars", type=int, default=0, help="pad span.input and gen_ai.prompt with this many characters")
    s.add_argument("--exception-event", action="store_true", help="error scenario: add a SYNTHETIC OTel exception event with a stack trace")
    s.add_argument("--trace-id"); s.add_argument("--parent-span-id")
    s.add_argument("--repeat", type=int, default=1, help="send the identical body this many times (same trace and span ids)")
    s.add_argument("--out", help="append one JSON line per request here (no header values)")
    a = ap.parse_args()

    headers = parse_headers(a.headers, a.header)
    if a.cmd == "probe":
        status, body = post(a.endpoint, bf.test_connection_request(), headers, gzip_body=a.gzip, test=True)
        ok = 200 <= status < 300 or status == 400
        print(json.dumps({"cmd": "probe", "status": status, "passes_openrouter_rule": ok, "body": body[:200]}))
        return 0 if ok else 1

    resource = dict(item.split("=", 1) for item in a.resource)
    rc = 0
    for g in scenario_generations(a):
        body = bf.build_request(g, resource)
        trace_id = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
        for i in range(a.repeat):
            status, resp = post(a.endpoint, body, headers, gzip_body=a.gzip)
            line = {"cmd": "send", "scenario": a.scenario, "status": status, "trace_id": trace_id, "attempt": i + 1,
                    "model": g.model, "tokens": [g.input_tokens, g.output_tokens], "body": resp[:160] if status >= 300 or status == 0 else ""}
            print(json.dumps(line))
            if a.out:
                with open(a.out, "a") as f:
                    f.write(json.dumps(line) + "\n")
            if not 200 <= status < 300:
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
