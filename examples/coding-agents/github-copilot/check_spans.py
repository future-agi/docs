#!/usr/bin/env python3
"""Check Copilot CLI or VS Code OTel file-exporter JSON lines.

The CLI exporter writes records as ``{"type":"span", ...}``; the VS Code
FileSpanExporter writes span objects directly. This local pre-flight check
normalizes both shapes. The setup path remains OTLP/HTTP straight to Future AGI.
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


def _attrs(span: dict) -> dict:
    attrs = span.get("attributes", {})
    if isinstance(attrs, dict):
        return attrs
    if isinstance(attrs, list):
        out = {}
        for item in attrs:
            if not isinstance(item, dict) or "key" not in item:
                continue
            value = item.get("value", {})
            if isinstance(value, dict) and value:
                out[item["key"]] = next(iter(value.values()))
        return out
    return {}


def _parent(span: dict) -> str | None:
    if span.get("parentSpanId"):
        return span["parentSpanId"]
    context = span.get("parentSpanContext")
    return context.get("spanId") if isinstance(context, dict) else None


def load_spans(path: str) -> list[dict]:
    spans = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            # CLI: type=span. VS Code: direct span object with spanId.
            if record.get("type") == "span" or record.get("spanId"):
                copy = dict(record)
                copy["attributes"] = _attrs(record)
                copy["parentSpanId"] = _parent(record)
                spans.append(copy)
    return spans


def check(spans: list[dict], content: bool = False, marker: str | None = None, raw: str = "") -> list[str]:
    errors: list[str] = []
    if not spans:
        return ["no spans in file"]
    for span in spans:
        span["attributes"] = _attrs(span)
    ids = {s["spanId"] for s in spans}
    # Standalone non-agent roots such as custom_notification are valid vendor
    # records but are outside this recipe's agent-tree contract.
    relevant = [s for s in spans if s["attributes"].get("gen_ai.operation.name") in
                {"invoke_agent", "chat", "execute_tool"}]
    roots = [s for s in relevant if not s.get("parentSpanId") or s["parentSpanId"] not in ids]
    for root in roots:
        if root["attributes"].get("gen_ai.operation.name") != "invoke_agent":
            errors.append(f"root span {root['name']!r} is not invoke_agent")
    traces = {s["traceId"] for s in relevant}
    if len(roots) != len(traces):
        errors.append(f"{len(traces)} agent trace(s) but {len(roots)} invoke_agent root(s)")
    ops = {s["attributes"].get("gen_ai.operation.name") for s in relevant}
    for needed in ("invoke_agent", "chat", "execute_tool"):
        if needed not in ops:
            errors.append(f"no {needed} span")
    for s in relevant:
        attrs = s["attributes"]
        if not attrs.get("gen_ai.conversation.id"):
            errors.append(f"span {s['name']!r} has no gen_ai.conversation.id")
        if attrs.get("gen_ai.operation.name") == "execute_tool" and not attrs.get("gen_ai.tool.name"):
            errors.append(f"tool span {s['spanId']} has no gen_ai.tool.name")
    present = sorted({k for s in relevant for k in s["attributes"] if k in CONTENT_ATTRS})
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
