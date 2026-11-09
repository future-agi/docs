#!/usr/bin/env python3
"""Send a fixed set of requests through a running LiteLLM Proxy (stdlib only).

Each scenario prints one JSON line: its name, the HTTP status the proxy returned and the
``x-litellm-call-id`` header. Run it after the proxy is up, then look at the traces.

Scenarios
  plain      one chat completion
  stream     the same, streamed, asking for usage in the last chunk
  tools      a tool call and its tool result (two requests); the model sees a tool definition
  error      the upstream returns HTTP 500 (needs the mock upstream: it fails on FAIL_UPSTREAM)
  unreachable  the model's upstream refuses the connection
  joined     a request carrying a W3C ``traceparent``; the printed trace_id is the one it joins
  headers    a request carrying cookie / custom headers, to see whether any reach the trace
  badkey     a request with a wrong proxy key (proxy rejects it, HTTP 401)

Usage
  python3 send_requests.py --proxy http://127.0.0.1:4000 --key sk-... --marker MARK_abc123
  python3 send_requests.py ... --only plain,stream
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request

SCENARIOS = ["plain", "stream", "tools", "error", "unreachable", "joined", "headers", "badkey"]


def post(base: str, key: str, body: dict, extra_headers: dict | None = None, timeout: float = 120.0):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    headers.update(extra_headers or {})
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        try:
            return err.code, dict(err.headers), err.read()
        finally:
            err.close()


def emit(name: str, status: int, headers: dict, **extra) -> None:
    lowered = {k.lower(): v for k, v in headers.items()}
    print(json.dumps({"scenario": name, "status": status, "call_id": lowered.get("x-litellm-call-id"), **extra}), flush=True)


def run(args: argparse.Namespace) -> int:
    wanted = [s for s in (args.only.split(",") if args.only else SCENARIOS) if s]
    unknown = [s for s in wanted if s not in SCENARIOS]
    if unknown:
        print(f"unknown scenario(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    marker = args.marker
    base, key, model = args.proxy, args.key, args.model
    user = {"role": "user", "content": f"Look up the weather for {marker}"}
    tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Look up the weather",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    }
    for name in wanted:
        if name == "plain":
            status, headers, _ = post(base, key, {"model": model, "messages": [user]})
            emit(name, status, headers)
        elif name == "stream":
            status, headers, _ = post(
                base, key, {"model": model, "messages": [user], "stream": True, "stream_options": {"include_usage": True}}
            )
            emit(name, status, headers)
        elif name == "tools":
            status, headers, raw = post(base, key, {"model": model, "messages": [user], "tools": [tool]})
            emit("tools.call", status, headers)
            try:
                call = json.loads(raw)["choices"][0]["message"]["tool_calls"][0]
            except Exception:
                call = None
            if call:
                followup = [
                    user,
                    {"role": "assistant", "content": None, "tool_calls": [call]},
                    {"role": "tool", "tool_call_id": call["id"], "content": f"sunny and 21C for {marker}"},
                ]
                status, headers, _ = post(base, key, {"model": model, "messages": followup, "tools": [tool]})
                emit("tools.result", status, headers)
        elif name == "error":
            bad = {"role": "user", "content": f"FAIL_UPSTREAM {marker}"}
            status, headers, _ = post(base, key, {"model": model, "messages": [bad]})
            emit(name, status, headers)
        elif name == "unreachable":
            status, headers, _ = post(base, key, {"model": args.unreachable_model, "messages": [user]})
            emit(name, status, headers)
        elif name == "joined":
            trace_id = secrets.token_hex(16)
            parent = secrets.token_hex(8)
            status, headers, _ = post(
                base, key, {"model": model, "messages": [user]}, {"traceparent": f"00-{trace_id}-{parent}-01"}
            )
            emit(name, status, headers, trace_id=trace_id, parent_span_id=parent)
        elif name == "headers":
            extra = {
                "Cookie": f"session=COOKIE_{marker}",
                "X-Forwarded-For": "203.0.113.7",
                "X-Custom-Token": f"CUSTOM_{marker}",
                "X-Api-Key": f"APIKEYHDR_{marker}",
            }
            status, headers, _ = post(base, key, {"model": model, "messages": [user]}, extra)
            emit(name, status, headers)
        elif name == "badkey":
            status, headers, _ = post(base, "sk-wrong-key-for-test", {"model": model, "messages": [user]})
            emit(name, status, headers)
    return 0


def main_with_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--proxy", default="http://127.0.0.1:4000")
    parser.add_argument("--key", required=True, help="the proxy master key (or a virtual key)")
    parser.add_argument("--model", default="demo-model")
    parser.add_argument("--unreachable-model", default="unreachable-model")
    parser.add_argument("--marker", default="MARK_" + secrets.token_hex(4))
    parser.add_argument("--only", default="", help="comma-separated scenario names")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main_with_args())
