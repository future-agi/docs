#!/usr/bin/env python3
"""Check a GitHub Copilot OTel span dump against the Future AGI recipe contract.

Input is the JSON-lines file Copilot writes when COPILOT_OTEL_FILE_EXPORTER_PATH
is set (one record per span or metric). This is a local pre-flight check only;
the setup path is OTLP/HTTP straight to Future AGI.

    python3 check_spans.py copilot-otel.jsonl [--content] [--marker TEXT]

Checks:
  * one trace per agent invocation, rooted at an `invoke_agent` span;
  * every `chat` / `execute_tool` span is a child of that root (or of a subagent);
  * every span carries `gen_ai.conversation.id`;
  * `execute_tool` spans carry `gen_ai.tool.name`;
  * with content capture off (default), no content attribute is present and the
    optional --marker string does not appear anywhere in the dump;
  * with --content, at least one content attribute is present.
"""
from __future__ import annotations

import argparse
import json
import sys

CONTENT_ATTRS = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.tool.definitions",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
)


def load_spans(path: str) -> list[dict]:
    spans = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                record = json.loads(line)
                if record.get("type") == "span":
                    spans.append(record)
    return spans


def check(spans: list[dict], content: bool = False, marker: str | None = None, raw: str = "") -> list[str]:
    errors: list[str] = []
    if not spans:
        return ["no spans in file"]
    ids = {s["spanId"] for s in spans}
    roots = [s for s in spans if not s.get("parentSpanId") or s["parentSpanId"] not in ids]
    for root in roots:
        if root["attributes"].get("gen_ai.operation.name") != "invoke_agent":
            errors.append(f"root span {root['name']!r} is not invoke_agent")
    traces = {s["traceId"] for s in spans}
    if len(roots) != len(traces):
        errors.append(f"{len(traces)} trace(s) but {len(roots)} root span(s)")
    ops = {s["attributes"].get("gen_ai.operation.name") for s in spans}
    for needed in ("invoke_agent", "chat", "execute_tool"):
        if needed not in ops:
            errors.append(f"no {needed} span")
    for s in spans:
        attrs = s["attributes"]
        if not attrs.get("gen_ai.conversation.id"):
            errors.append(f"span {s['name']!r} has no gen_ai.conversation.id")
        if attrs.get("gen_ai.operation.name") == "execute_tool" and not attrs.get("gen_ai.tool.name"):
            errors.append(f"tool span {s['spanId']} has no gen_ai.tool.name")
    present = sorted({k for s in spans for k in s["attributes"] if k in CONTENT_ATTRS})
    if content and not present:
        errors.append("content capture requested but no content attribute was exported")
    if not content and present:
        errors.append(f"content attributes present with capture off: {present}")
    if marker and not content and marker in raw:
        errors.append("prompt marker found in a default (content-off) export")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--content", action="store_true", help="expect content capture to be on")
    ap.add_argument("--marker", help="unique string from the prompt; must be absent when content is off")
    a = ap.parse_args()
    with open(a.path, encoding="utf-8") as fh:
        raw = fh.read()
    spans = load_spans(a.path)
    errors = check(spans, content=a.content, marker=a.marker, raw=raw)
    tools = sorted({s["attributes"].get("gen_ai.tool.name") for s in spans if s["attributes"].get("gen_ai.tool.name")})
    print(f"spans={len(spans)} traces={len({s['traceId'] for s in spans})} tools={tools}")
    for e in errors:
        print(f"FAIL: {e}")
    if not errors:
        print("PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
