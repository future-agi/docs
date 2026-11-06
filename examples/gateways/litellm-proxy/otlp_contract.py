#!/usr/bin/env python3
"""Read OTLP/JSON exported by LiteLLM Proxy and check it against the Future AGI ingest contract.

Stdlib only. Used by ``tests/test_contract.py`` (on committed captures) and by ``run_e2e.sh``
(on the capture the sink recorded). The rules mirror what the Future AGI collector does:

* every ResourceSpans must carry a string resource attribute ``project_name``
  (``fi-collector/pkg/auth/stamp.go``: the batch is rejected otherwise);
* only the traces signal is served, and this recipe sends uncompressed bodies;
* an LLM call is a span with ``gen_ai.operation.name`` (v2) and, for v1, ``litellm_request``.

CLI:  python3 otlp_contract.py check CAPTURE_DIR --mode v2 --content off --marker MARK_x
"""
from __future__ import annotations

import argparse
import base64
import binascii
import glob
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

HEX = set("0123456789abcdef")

# Attributes LiteLLM exports even with content capture off. They carry provider error text, Python
# stack traces (with file paths of the proxy host), the caller's address and user agent, and the
# upstream host. collector/otelcol-scrub.yaml removes them.
LEAKY_ATTRS = (
    "error.message",
    "litellm.provider.error.stack_trace",
    "net.peer.ip",
    "net.peer.port",
    "http.user_agent",
    "http.host",
    "http.server_name",
    "http.url",
    "server.address",
    "server.port",
    # v1 callback only
    "metadata.requester_ip_address",
    "metadata.user_agent",
    "metadata.requester_metadata",
    "hidden_params",
)
LEAKY_EVENT_ATTRS = ("exception.message", "exception.stacktrace")


def norm_id(value: str) -> str:
    """OTLP/JSON ids are hex; protobuf-to-JSON dumps give base64. Return hex either way."""
    if not value:
        return ""
    if len(value) in (16, 32) and set(value.lower()) <= HEX:
        return value.lower()
    try:
        return base64.b64decode(value).hex()
    except (binascii.Error, ValueError):
        return value


def any_value(v: dict) -> Any:
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "arrayValue" in v:
        return [any_value(x) for x in v["arrayValue"].get("values", [])]
    if "kvlistValue" in v:
        return {kv["key"]: any_value(kv["value"]) for kv in v["kvlistValue"].get("values", [])}
    return None


def attr_map(items: Iterable[dict] | None) -> dict:
    return {a["key"]: any_value(a["value"]) for a in items or []}


@dataclass
class Span:
    name: str
    kind: str
    status: str
    status_message: str
    trace_id: str
    span_id: str
    parent_id: str
    attrs: dict
    events: list
    resource: dict
    scope: str
    start_ns: int = 0
    children: list = field(default_factory=list)

    def text(self) -> str:
        return json.dumps(
            {"name": self.name, "attrs": self.attrs, "events": self.events, "status": self.status_message},
            sort_keys=True,
        )


def load_documents(path: str) -> list[dict]:
    """A capture directory (NNN-traces.json files from otlp_sink.py) or one merged JSON file."""
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*-traces.json")))
    else:
        files = [path]
    docs = []
    for name in files:
        with open(name) as fh:
            docs.append(json.load(fh))
    return docs


def resource_spans(docs: list[dict]) -> list[dict]:
    return [rs for doc in docs for rs in doc.get("resourceSpans", [])]


def flatten(docs: list[dict]) -> list[Span]:
    spans: list[Span] = []
    for rs in resource_spans(docs):
        resource = attr_map(rs.get("resource", {}).get("attributes"))
        for ss in rs.get("scopeSpans", []):
            scope = ss.get("scope", {}).get("name", "")
            for s in ss.get("spans", []):
                status = s.get("status", {})
                spans.append(
                    Span(
                        name=s["name"],
                        kind=s.get("kind", "").replace("SPAN_KIND_", ""),
                        status=status.get("code", "").replace("STATUS_CODE_", "") or "UNSET",
                        status_message=status.get("message", ""),
                        trace_id=norm_id(s["traceId"]),
                        span_id=norm_id(s["spanId"]),
                        parent_id=norm_id(s.get("parentSpanId", "")),
                        attrs=attr_map(s.get("attributes")),
                        events=[{"name": e["name"], "attrs": attr_map(e.get("attributes"))} for e in s.get("events", [])],
                        resource=resource,
                        scope=scope,
                        start_ns=int(s.get("startTimeUnixNano", 0)),
                    )
                )
    return spans


def traces(spans: list[Span]) -> dict[str, list[Span]]:
    by_trace: dict[str, list[Span]] = {}
    for s in spans:
        by_trace.setdefault(s.trace_id, []).append(s)
    for members in by_trace.values():
        ids = {m.span_id for m in members}
        for m in members:
            m.children = sorted(
                [c for c in members if c.parent_id == m.span_id], key=lambda c: c.start_ns
            ) if m.span_id in ids else []
    return by_trace


def roots(members: list[Span]) -> list[Span]:
    ids = {m.span_id for m in members}
    return sorted((m for m in members if m.parent_id not in ids), key=lambda m: m.start_ns)


def collector_accepts(docs: list[dict]) -> tuple[bool, str]:
    """Mirror of fi-collector StampResourceAttrs fail-fast: every ResourceSpans needs a string project_name."""
    missing = []
    for i, rs in enumerate(resource_spans(docs)):
        value = attr_map(rs.get("resource", {}).get("attributes")).get("project_name")
        if not isinstance(value, str) or not value:
            missing.append(i)
    if missing:
        return False, f"{len(missing)} ResourceSpans have no project_name (indices {missing[:5]})"
    return True, "every ResourceSpans carries project_name"


def llm_spans(spans: list[Span], mode: str) -> list[Span]:
    if mode == "v2":
        return [s for s in spans if s.attrs.get("gen_ai.operation.name") == "chat"]
    return [s for s in spans if s.name == "litellm_request" or s.name.startswith("chat ")]


def contains(spans: list[Span], needle: str) -> bool:
    return any(needle in s.text() or needle in json.dumps(s.resource) for s in spans)


def leaks(spans: list[Span]) -> list[str]:
    """Names of the content-off leaks present in the spans (see LEAKY_ATTRS)."""
    found: set[str] = set()
    for s in spans:
        found.update(k for k in LEAKY_ATTRS if k in s.attrs)
        if s.status == "ERROR" and s.status_message:
            found.add("status.message")
        for e in s.events:
            found.update(k for k in LEAKY_EVENT_ATTRS if k in e["attrs"])
    return sorted(found)


def request_log(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def check(capture: str, mode: str, content: str, marker: str, master_key: str = "", scrubbed: bool = False) -> list[tuple[bool | None, str]]:
    """Return (passed, message) lines; passed is None for an informational line. ``content`` is 'off' or 'on'."""
    results: list[tuple[bool | None, str]] = []  # ok is None for an informational line

    def record(ok: bool | None, msg: str) -> None:
        results.append((None if ok is None else bool(ok), msg))

    docs = load_documents(capture)
    spans = flatten(docs)
    record(bool(spans), f"{len(spans)} spans exported")
    log = request_log(os.path.join(capture, "requests.jsonl")) if os.path.isdir(capture) else []
    if log:
        record(all(r["signal"] == "traces" for r in log), f"only /v1/traces requests: {sorted({r['path'] for r in log})}")
        record(all(not r["content_encoding"] for r in log), "no request is compressed (no Content-Encoding)")
        record(
            all({"x-api-key", "x-secret-key"} <= set(r["auth_headers_present"]) for r in log),
            "X-Api-Key and X-Secret-Key present on every request",
        )
    ok, msg = collector_accepts(docs)
    record(ok, msg)
    calls = llm_spans(spans, mode)
    record(bool(calls), f"{len(calls)} LLM-call spans ({'chat <model>' if mode == 'v2' else 'litellm_request'})")
    done = [s for s in calls if s.status != "ERROR"]
    record(
        bool(done) and all(s.attrs.get("gen_ai.request.model") for s in done),
        "model present on every successful LLM-call span",
    )
    record(
        bool(done) and all(s.attrs.get("gen_ai.usage.input_tokens") is not None and s.attrs.get("gen_ai.usage.output_tokens") is not None for s in done),
        "input and output tokens present on every successful LLM-call span",
    )
    if mode == "v2":
        record(
            all(s.kind == "CLIENT" for s in calls),
            "v2 LLM-call spans are CLIENT spans named 'chat <model>' with gen_ai.operation.name=chat",
        )
    if marker:
        found = contains(spans, marker)
        if content == "off":
            record(not found, f"content off: marker {marker} not in any span, event or resource attribute")
        else:
            record(found, f"content on: marker {marker} present")
    if master_key:
        record(not contains(spans, master_key), "proxy master key not in any exported attribute")
    record(not contains(spans, "uthorization"), "no Authorization header value or name in any attribute")
    present = leaks(spans)
    if scrubbed:
        record(not present, f"scrubbed: none of the error-text, stack-trace or address attributes remain {present or ''}".strip())
    else:
        record(None, f"attributes present even with content off (see the page): {present or 'none'}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    chk = sub.add_parser("check")
    chk.add_argument("capture", help="directory written by otlp_sink.py, or a merged OTLP/JSON file")
    chk.add_argument("--mode", choices=["v1", "v2"], default="v2")
    chk.add_argument("--content", choices=["off", "on"], default="off")
    chk.add_argument("--marker", default="")
    chk.add_argument("--master-key", default="")
    chk.add_argument("--scrubbed", action="store_true", help="the capture was taken after collector/otelcol-scrub.yaml")
    args = parser.parse_args()
    failed = 0
    for ok, msg in check(args.capture, args.mode, args.content, args.marker, args.master_key, args.scrubbed):
        print(("INFO  " if ok is None else "PASS  " if ok else "FAIL  ") + msg)
        failed += 1 if ok is False else 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
