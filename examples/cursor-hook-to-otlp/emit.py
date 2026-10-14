#!/usr/bin/env python3
"""Cursor hook -> OTLP/HTTP exporter.

The default mode records session/tool metadata only. It never forwards hook
payload bodies, prompts, tool arguments, tool results, or error messages.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

SECRET_PATTERNS = (
    re.compile(r"(?i)(sk-[A-Za-z0-9_-]{12,})"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,}]+"),
)


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()


def _redact(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda m: m.group(1) + "[REDACTED]" if m.lastindex else "[REDACTED]", value)
    return value


def _safe_content(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = _redact(text)
    return text[:4096]


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    return {"key": key, "value": {"stringValue": str(value)}}


def _first(payload: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return default


def _span_id(event: str, payload: dict[str, Any]) -> str:
    seed = f"{event}:{time.time_ns()}:{os.getpid()}:{_sha(payload)}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]


def _trace_id(payload: dict[str, Any]) -> str:
    session = _first(payload, "conversation_id", "session_id", "session.id", default="cursor-unknown")
    return hashlib.sha256(str(session).encode()).hexdigest()[:32]


def _span(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _first(payload, "conversation_id", "session_id", "session.id", default="unknown")
    tool_name = _first(payload, "tool_name", "tool", "toolName", default="unknown")
    name = "cursor.session" if event == "stop" else f"cursor.tool.{tool_name}"
    now = time.time_ns()
    attrs = [
        _attr("session.id", session),
        _attr("gen_ai.conversation.id", session),
        _attr("cursor.hook.name", event),
        _attr("cursor.tool.name", tool_name),
    ]
    for source, target in (("generation_id", "cursor.generation.id"), ("model", "gen_ai.request.model"),
                           ("model_id", "cursor.model.id"), ("status", "cursor.status"),
                           ("error_count", "cursor.error.count"), ("loop_count", "cursor.loop.count")):
        if payload.get(source) not in (None, ""):
            attrs.append(_attr(target, payload[source]))
    if event != "stop":
        raw_input = _first(payload, "tool_input", "input", "command", default="")
        attrs.extend([
            _attr("cursor.tool.input.bytes", len(json.dumps(raw_input, ensure_ascii=False).encode("utf-8"))),
            _attr("cursor.tool.input.sha256", _sha(raw_input)),
        ])
        if _env_bool("CURSOR_CAPTURE_CONTENT"):
            for source, target in (("tool_input", "cursor.tool.input"), ("tool_output", "cursor.tool.output"), ("result", "cursor.tool.output")):
                if payload.get(source) not in (None, ""):
                    attrs.append(_attr(target, _safe_content(payload[source])))
    if event == "stop":
        for key, attr_name in (("tool_count", "cursor.tool.count"), ("duration_ms", "cursor.duration.ms")):
            if payload.get(key) not in (None, ""):
                attrs.append(_attr(attr_name, payload[key]))
        if _env_bool("CURSOR_CAPTURE_CONTENT"):
            for source, target in (("prompt", "gen_ai.prompt"), ("response", "gen_ai.completion"), ("error", "error.message")):
                if payload.get(source) not in (None, ""):
                    attrs.append(_attr(target, _safe_content(payload[source])))
    status = str(_first(payload, "status", default=("ERROR" if event == "postToolUseFailure" else "OK"))).upper()
    span: dict[str, Any] = {
        "traceId": _trace_id(payload),
        "spanId": _span_id(event, payload),
        "name": name,
        "kind": 1,
        "startTimeUnixNano": str(now),
        "endTimeUnixNano": str(time.time_ns()),
        "attributes": attrs,
        "status": {"code": 2 if status in {"ERROR", "FAILED", "CANCELLED"} else 1},
    }
    if status in {"ERROR", "FAILED", "CANCELLED"}:
        span["status"]["message"] = "error details omitted by default"
    return span


def build_request(event: str, payload: dict[str, Any]) -> bytes:
    endpoint = os.getenv("FI_OTLP_ENDPOINT", "https://api.futureagi.com/tracer/v1/traces").rstrip("/")
    if not endpoint.endswith("/v1/traces"):
        endpoint += "/v1/traces"
    attrs = [
        _attr("service.name", "cursor-ide"),
        _attr("service.version", "cursor-hook-to-otlp"),
        _attr("project_name", os.environ["FI_PROJECT_NAME"]),
        _attr("project_type", "observe"),
    ]
    body = {"resourceSpans": [{"resource": {"attributes": attrs}, "scopeSpans": [{
        "scope": {"name": "futureagi.cursor.hook", "version": "1.0.0"},
        "spans": [_span(event, payload)],
    }]}]}
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": os.environ["FI_API_KEY"],
        "X-Secret-Key": os.environ["FI_SECRET_KEY"],
    }
    req = urllib.request.Request(endpoint, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("FI_OTLP_TIMEOUT", "10"))) as response:
            if response.status >= 300:
                raise RuntimeError(f"collector returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"collector returned HTTP {exc.code}") from exc
    return json.dumps(body).encode()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: emit.py <stop|preToolUse|postToolUse|postToolUseFailure>", file=sys.stderr)
        return 2
    event = sys.argv[1]
    if event not in {"stop", "preToolUse", "postToolUse", "postToolUseFailure"}:
        print("unsupported hook event", file=sys.stderr)
        return 2
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        for required in ("FI_API_KEY", "FI_SECRET_KEY", "FI_PROJECT_NAME"):
            if not os.getenv(required):
                raise ValueError(f"missing {required}")
        build_request(event, payload)
        print("{}")
        return 0
    except Exception as exc:
        # Never echo payloads, URLs, header values, or exception text from a
        # vendor/client that might contain user content.
        print(f"cursor hook export failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
