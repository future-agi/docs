#!/usr/bin/env python3
"""Claude Cowork OpenTelemetry log events -> Future AGI traces, content stripped.

Cowork exports OTel log events (user_prompt, assistant_response, api_request,
api_error, tool_result, tool_decision), all linked by prompt.id, to the OTLP
endpoint an admin sets in the Claude admin console. The Future AGI collector
ingests traces only, so this bridge receives those events and turns every
prompt into one trace:

    Cowork prompt (agent)              one prompt.id, session.id
    |-- Cowork model request (llm)     api_request / api_error
    |-- Read (tool)                    tool_result, tool_decision
    `-- Cowork model request (llm)

Spans are built from an allow-list of metadata fields. Prompt text, model
response text, tool_input, tool error text, the API's error message,
user.email, workspace.host_paths, enduser.id and process.owner are never
forwarded by default, even when the admin's device config exports them. From
tool_parameters only four name keys are read (mcp_server_name, mcp_tool_name,
skill_name, subagent_type), and a value that looks like a path or an email is
dropped; commands, file paths and every other key stay out.
FI_BRIDGE_CAPTURE_CONTENT=1 adds the prompt, the response, tool_input and the
error messages; user.email, workspace.host_paths, enduser.id and process.owner
are never sent.

Only records whose resource service.name is `cowork` are used, so a Claude
Code exporter pointed here by mistake is ignored (FI_BRIDGE_ACCEPT_ANY_SERVICE=1
turns that check off for tests).

Delivery is at least once on Cowork's side. A record identical to one already
received for the same prompt is skipped, so a re-sent batch does not double
the prompt's totals.

Stdlib only, Python 3.9+. Accepts OTLP/HTTP JSON (choose HTTP/JSON in the
admin form), plain, gzip-encoded or chunked; HTTP/protobuf works when
opentelemetry-proto is installed.

Environment:
    FI_API_KEY, FI_SECRET_KEY     Future AGI keys (required)
    FI_PROJECT_NAME               project (default: claude-cowork)
    FI_BASE_URL                   default https://api.futureagi.com; traces go to $FI_BASE_URL/tracer/v1/traces
    FI_OTLP_ENDPOINT              full traces URL, overrides FI_BASE_URL
    FI_BRIDGE_LISTEN              host:port to listen on (default 127.0.0.1:4320)
    FI_BRIDGE_TOKEN               shared secret; requests must send "Authorization: Bearer <token>".
                                  Required: the bridge will not start without it ...
    FI_BRIDGE_ALLOW_NO_TOKEN      ... unless this is 1 (local tests only)
    FI_BRIDGE_IDLE_SECONDS        a prompt is sent this long after its last event (default 10)
    FI_BRIDGE_CAPTURE_CONTENT     1 = keep prompt, response, tool_input and error text
    FI_BRIDGE_MAX_CONTENT_CHARS   per-field cap when content is on (default 4096)
    FI_BRIDGE_ACCEPT_ANY_SERVICE  1 = accept records from any service.name (tests only)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

SCOPE = {"name": "fi-cowork-bridge", "version": "1.1.0"}
SERVICE = "cowork"
EVENTS = ("user_prompt", "assistant_response", "api_request", "api_error", "tool_result", "tool_decision")
REDACTED = ("<REDACTED>", "[REDACTED]", "")
LOOPBACK = ("127.0.0.1", "localhost", "::1")
# The only tool_parameters keys read: names, never arguments.
NAME_KEYS = (("mcp_server_name", "cowork.mcp_server_name"), ("mcp_tool_name", "cowork.mcp_tool_name"),
             ("skill_name", "cowork.skill_name"), ("subagent_type", "cowork.subagent_type"))
IDENTITY = ("session.id", "gen_ai.conversation.id", "user.id")
# Anthropic API error types (https://docs.anthropic.com/en/api/errors): a fixed enum, safe to export.
API_ERROR_TYPE = re.compile(r"\b(invalid_request_error|authentication_error|permission_error|not_found_error|"
                            r"request_too_large|rate_limit_error|api_error|overloaded_error|billing_error|"
                            r"timeout_error)\b")
MAX_BODY = 16 * 1024 * 1024  # bytes, before and after gzip
READ_TIMEOUT = 30  # seconds a client may stall while sending a request


def flag(e: Dict[str, str], key: str) -> bool:
    return e.get(key, "").strip().lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self, environ: Optional[Dict[str, str]] = None):
        e = dict(os.environ if environ is None else environ)
        self.api_key = e.get("FI_API_KEY", "")
        self.secret_key = e.get("FI_SECRET_KEY", "")
        self.project = e.get("FI_PROJECT_NAME") or "claude-cowork"
        base = (e.get("FI_BASE_URL") or "https://api.futureagi.com").rstrip("/")
        self.endpoint = e.get("FI_OTLP_ENDPOINT") or base + "/tracer/v1/traces"
        self.listen = e.get("FI_BRIDGE_LISTEN") or "127.0.0.1:4320"
        self.token = e.get("FI_BRIDGE_TOKEN", "")
        self.allow_no_token = flag(e, "FI_BRIDGE_ALLOW_NO_TOKEN")
        self.idle = float(e.get("FI_BRIDGE_IDLE_SECONDS") or 10)
        self.capture = flag(e, "FI_BRIDGE_CAPTURE_CONTENT")
        self.max_chars = int(e.get("FI_BRIDGE_MAX_CONTENT_CHARS") or 4096)
        self.any_service = flag(e, "FI_BRIDGE_ACCEPT_ANY_SERVICE")


# ---------------------------------------------------------------- OTLP input

def any_value(v: Any) -> Any:
    if not isinstance(v, dict):
        return v
    for k in ("stringValue", "boolValue", "doubleValue"):
        if k in v:
            return v[k]
    if "intValue" in v:
        return int(v["intValue"])
    if "arrayValue" in v:
        return [any_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def kv(items) -> Dict[str, Any]:
    return {a["key"]: any_value(a.get("value", {})) for a in items or []}


def event_name(attrs: Dict[str, Any], record: Dict[str, Any]) -> str:
    """Documented as e.g. `user_prompt`; accept a prefixed form (`cowork.user_prompt`) too."""
    for raw in (attrs.get("event.name"), record.get("eventName"), any_value(record.get("body") or {})):
        if isinstance(raw, str) and raw:
            name = raw.rsplit(".", 1)[-1]
            if name in EVENTS:
                return name
    return ""


def event_time(attrs: Dict[str, Any], record: Dict[str, Any]) -> int:
    ts = attrs.get("event.timestamp")
    if isinstance(ts, str) and ts:
        try:
            return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1e9)
        except ValueError:
            pass
    for k in ("timeUnixNano", "observedTimeUnixNano"):
        if to_int(record.get(k)):
            return int(record[k])
    return time.time_ns()


def log_events(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = []
    for rl in body.get("resourceLogs", []):
        resource = kv(rl.get("resource", {}).get("attributes"))
        for sl in rl.get("scopeLogs", []):
            for rec in sl.get("logRecords", []):
                attrs = kv(rec.get("attributes"))
                name = event_name(attrs, rec)
                if name and attrs.get("prompt.id"):
                    events.append({"name": name, "attrs": attrs, "time": event_time(attrs, rec),
                                   "resource": resource, "service": str(resource.get("service.name") or ""),
                                   "seq": to_int(attrs.get("event.sequence")) or 0})
    events.sort(key=lambda e: (e["time"], e["seq"]))
    return events


# ---------------------------------------------------------------- mapping

def hexid(*parts: Any, size: int = 8) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[: size * 2]


def trace_id_for(prompt_id: str) -> str:
    """prompt.id is a UUID v4: its 32 hex digits are the trace id."""
    h = prompt_id.replace("-", "").lower()
    if len(h) == 32 and all(c in "0123456789abcdef" for c in h):
        return h
    return hexid("cowork-prompt", prompt_id, size=16)


def to_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def tool_names(a: Dict[str, Any]) -> Dict[str, str]:
    """Name keys from tool_parameters; everything else in it (commands, paths, URLs) is ignored."""
    raw = a.get("tool_parameters")
    if not isinstance(raw, str):
        return {}
    try:
        params = json.loads(raw)
    except ValueError:
        return {}
    out = {}
    if isinstance(params, dict):
        for src, dst in NAME_KEYS:
            v = params.get(src)
            # A name, not a path, an email or free text.
            if isinstance(v, str) and 0 < len(v) <= 128 and not any(c in v for c in "/\\@\n\r\t"):
                out[dst] = v
    return out


def tool_label(tool_name: str, names: Dict[str, str]) -> str:
    """MCP calls arrive as tool_name "mcp_tool"; name them mcp__<server>__<tool> when the names are known."""
    server, tool = names.get("cowork.mcp_server_name"), names.get("cowork.mcp_tool_name")
    return f"mcp__{server}__{tool}" if server and tool else tool_name


def api_error_summary(status: Optional[int], error: Any) -> Tuple[str, Optional[str]]:
    """Status message and error.type for an api_error with content off: HTTP status + Anthropic error type."""
    m = API_ERROR_TYPE.search(error) if isinstance(error, str) else None
    etype = m.group(1) if m else None
    parts = [f"HTTP {status}" if status else "", etype or ""]
    return " ".join(p for p in parts if p) or "model request failed", etype


class Span:
    def __init__(self, trace_id: str, span_id: str, parent: Optional[str], name: str, kind: str, start: int, end: int,
                 seq: int = 0):
        self.trace_id, self.span_id, self.parent, self.name = trace_id, span_id, parent, name
        self.start, self.end, self.seq = start, end, seq
        self.attrs: Dict[str, Any] = {"fi.span.kind": kind}
        self.error: Optional[str] = None
        self.from_result = False
        self.sent = False

    def otlp(self) -> Dict[str, Any]:
        attrs = []
        for k, v in self.attrs.items():
            if v is None:
                continue
            if isinstance(v, bool):
                val = {"boolValue": v}
            elif isinstance(v, int):
                val = {"intValue": str(v)}
            elif isinstance(v, float):
                val = {"doubleValue": v}
            else:
                val = {"stringValue": str(v)}
            attrs.append({"key": k, "value": val})
        span = {"traceId": self.trace_id, "spanId": self.span_id, "name": self.name, "kind": 1,
                "startTimeUnixNano": str(self.start), "endTimeUnixNano": str(max(self.start, self.end)),
                "attributes": attrs}
        if self.parent:
            span["parentSpanId"] = self.parent
        if self.error is not None:
            span["status"] = {"code": 2, "message": self.error}
        return span


class Prompt:
    def __init__(self, prompt_id: str, t: int):
        self.trace_id = trace_id_for(prompt_id)
        self.root = Span(self.trace_id, hexid("root", prompt_id), None, "Cowork prompt", "AGENT", t, t)
        self.root.attrs["cowork.prompt_id"] = prompt_id
        self.children: List[Span] = []
        self.decisions: List[Dict[str, Any]] = []
        self.seen: set = set()
        self.last_event = time.monotonic()
        self.dirty = True
        self.version: Optional[str] = None
        self.service = SERVICE

    def touch(self, t: int):
        self.root.start = min(self.root.start, t) if not self.root.sent else self.root.start
        self.root.end = max(self.root.end, t)
        self.last_event = time.monotonic()
        self.dirty = True


class CoworkMapper:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.prompts: Dict[str, Prompt] = {}
        self.lock = threading.Lock()

    def content(self, value: Any) -> Optional[str]:
        if not self.cfg.capture or value is None or value in REDACTED:
            return None
        s = str(value)
        return s if len(s) <= self.cfg.max_chars else s[: self.cfg.max_chars] + "...[truncated]"

    def add(self, events: List[Dict[str, Any]]):
        with self.lock:
            for ev in events:
                a, t, name = ev["attrs"], ev["time"], ev["name"]
                pid = str(a["prompt.id"])
                p = self.prompts.get(pid)
                if p is None:
                    p = self.prompts[pid] = Prompt(pid, t)
                # At-least-once delivery: an identical record is the same event sent again.
                key = hexid(name, t, json.dumps(a, sort_keys=True, default=str))
                if key in p.seen:
                    continue
                p.seen.add(key)
                p.version = ev["resource"].get("service.version") or p.version
                p.service = ev["service"] or p.service
                self.metadata(p.root, a)
                getattr(self, name)(p, a, t, ev["seq"])
                p.touch(t)

    def metadata(self, root: Span, a: Dict[str, Any]):
        """Allow-listed identifiers. Never: user.email, user.account_id, workspace.host_paths, enduser.id,
        process.owner, and not the device-level user.id either (the account UUID is the user)."""
        for src, dst in (("session.id", "session.id"), ("session.id", "gen_ai.conversation.id"),
                         ("user.account_uuid", "user.id"), ("organization.id", "cowork.organization_id"),
                         ("terminal.type", "cowork.terminal_type")):
            if a.get(src) and dst not in root.attrs:
                root.attrs[dst] = a[src]

    def user_prompt(self, p: Prompt, a: Dict[str, Any], t: int, seq: int):
        p.root.start = t if not p.root.sent else p.root.start
        p.root.attrs.update({"cowork.prompt_length": to_int(a.get("prompt_length")),
                             "input.value": self.content(a.get("prompt"))})

    def assistant_response(self, p: Prompt, a: Dict[str, Any], t: int, seq: int):
        p.root.attrs.update({"gen_ai.request.model": a.get("model"),
                             "cowork.response_length": to_int(a.get("response_length")),
                             "output.value": self.content(a.get("response"))})

    def llm_span(self, p: Prompt, a: Dict[str, Any], t: int, seq: int) -> Span:
        dur = to_int(a.get("duration_ms")) or 0
        span = Span(p.trace_id, hexid("llm", p.trace_id, a.get("event.sequence"), t), p.root.span_id,
                    "Cowork model request", "LLM", t - dur * 1_000_000, t, seq)
        span.attrs.update({"gen_ai.request.model": a.get("model"), "gen_ai.system": "anthropic",
                           "cowork.speed": a.get("speed"), "cowork.attempt": to_int(a.get("attempt"))})
        p.children.append(span)
        p.root.attrs.setdefault("gen_ai.request.model", a.get("model"))
        return span

    def api_request(self, p: Prompt, a: Dict[str, Any], t: int, seq: int):
        span = self.llm_span(p, a, t, seq)
        inp, out = to_int(a.get("input_tokens")), to_int(a.get("output_tokens"))
        cr, cc = to_int(a.get("cache_read_tokens")), to_int(a.get("cache_creation_tokens"))
        total_in = None if inp is None else inp + (cr or 0) + (cc or 0)  # Anthropic reports cache separately
        span.attrs.update({"gen_ai.usage.input_tokens": total_in, "gen_ai.usage.output_tokens": out,
                           "gen_ai.usage.cache_read.input_tokens": cr,
                           "gen_ai.usage.cache_creation.input_tokens": cc,
                           "gen_ai.cost.total": to_float(a.get("cost_usd"))})

    def api_error(self, p: Prompt, a: Dict[str, Any], t: int, seq: int):
        span = self.llm_span(p, a, t, seq)
        status = to_int(a.get("status_code"))
        summary, etype = api_error_summary(status, a.get("error"))
        span.attrs.update({"http.response.status_code": status, "error.type": etype})
        # The API's free-text message can echo request fragments, hosts or paths: content opt-in only.
        span.error = (self.content(a.get("error")) or summary)[:512]

    def tool_decision(self, p: Prompt, a: Dict[str, Any], t: int, seq: int):
        p.decisions.append({"tool_name": str(a.get("tool_name") or "tool"), "names": tool_names(a),
                            "decision": a.get("decision"), "source": a.get("source"),
                            "tool_use_id": a.get("tool_use_id"), "time": t})

    def match_decision(self, p: Prompt, name: str, names: Dict[str, str], a: Dict[str, Any], t: int):
        """The tool_decision event for this tool_result, if one is pending: by tool_use_id, else by tool
        name and decision_type. A result that carries neither pairs with nothing, so a pending reject
        is never consumed by a guess and still gets its own span."""
        use_id = a.get("tool_use_id")
        if use_id:
            for d in p.decisions:
                if d["tool_use_id"] == use_id:
                    return d
        want = a.get("decision_type")
        if not want:
            return None
        # A rejected call that the agent retried must keep its own reject span.
        return next((d for d in p.decisions
                     if d["tool_name"] == name and d["time"] <= t and d["decision"] == want
                     and not (use_id and d["tool_use_id"])
                     and all(d["names"].get(k) == v for k, v in names.items() if k in d["names"])), None)

    def tool_result(self, p: Prompt, a: Dict[str, Any], t: int, seq: int):
        dur = to_int(a.get("duration_ms")) or 0
        name = str(a.get("tool_name") or "tool")
        names = tool_names(a)
        label = tool_label(name, names)
        span = Span(p.trace_id, hexid("tool", p.trace_id, a.get("event.sequence"), name, t), p.root.span_id,
                    label, "TOOL", t - dur * 1_000_000, t, seq)
        span.from_result = True
        span.attrs.update({
            "gen_ai.tool.name": label,
            "cowork.tool_name": name,
            **names,
            "cowork.success": a.get("success"),
            "cowork.decision": a.get("decision_type"),
            "cowork.decision_source": a.get("decision_source"),
            "cowork.tool_result_size_bytes": to_int(a.get("tool_result_size_bytes")),
            "cowork.mcp_server_scope": a.get("mcp_server_scope"),
            "input.value": self.content(a.get("tool_input")),
        })
        d = self.match_decision(p, name, names, a, t)
        if d is not None:
            p.decisions.remove(d)
        if str(a.get("success")).lower() == "false":
            span.error = self.content(a.get("error")) or "tool failed"
        p.children.append(span)

    def rejected(self, p: Prompt):
        """Rejected tool calls have a tool_decision and no tool_result."""
        for d in p.decisions:
            if d["decision"] == "reject":
                label = tool_label(d["tool_name"], d["names"])
                span = Span(p.trace_id, hexid("decision", p.trace_id, d["tool_name"], d["time"]), p.root.span_id,
                            label, "TOOL", d["time"], d["time"])
                span.attrs.update({"gen_ai.tool.name": label, "cowork.tool_name": d["tool_name"], **d["names"],
                                   "cowork.decision": "reject", "cowork.decision_source": d["source"]})
                p.children.append(span)
        p.decisions = []

    def due(self, force: bool = False) -> List[Prompt]:
        with self.lock:
            now = time.monotonic()
            out = [p for p in self.prompts.values() if p.dirty and (force or now - p.last_event >= self.cfg.idle)]
            for pid, p in list(self.prompts.items()):
                if not p.dirty and now - p.last_event > 3600:
                    del self.prompts[pid]
            return out

    def spans(self, p: Prompt) -> List[Span]:
        """The prompt span plus children not sent yet. A prompt sent again keeps its span ids."""
        with self.lock:
            self.rejected(p)
            for c in p.children:
                if not p.root.sent:
                    p.root.start = min(p.root.start, c.start)
                p.root.end = max(p.root.end, c.end)
            # Prompt totals under cowork.* keys: gen_ai.usage.* on the prompt span
            # would be counted a second time in the trace's token total.
            llms = sorted((c for c in p.children if c.attrs["fi.span.kind"] == "LLM"), key=lambda c: (c.end, c.seq))
            used = [c for c in llms if c.error is None]
            if used:
                for key, src in (("cowork.prompt.input_tokens", "gen_ai.usage.input_tokens"),
                                 ("cowork.prompt.output_tokens", "gen_ai.usage.output_tokens")):
                    p.root.attrs[key] = sum(c.attrs.get(src) or 0 for c in used)
            # A failed model request that Cowork retried successfully stays ERROR on its own span only.
            p.root.error = "model request failed" if llms and llms[-1].error is not None else None
            # Tools that ran: a tool_result whose decision was reject never executed.
            p.root.attrs["cowork.tool_calls"] = sum(1 for c in p.children
                                                    if c.from_result and c.attrs.get("cowork.decision") != "reject")
            out = [p.root] + [c for c in p.children if not c.sent]
            for c in out[1:]:  # session and user on every span, as the family emitter does
                for k in IDENTITY:
                    if p.root.attrs.get(k) and k not in c.attrs:
                        c.attrs[k] = p.root.attrs[k]
            for s in out:
                s.sent = True
            p.dirty = False
            return out


# ---------------------------------------------------------------- export

class Bridge:
    def __init__(self, cfg: Config):
        self.cfg, self.mapper = cfg, CoworkMapper(cfg)
        self.stop = threading.Event()
        self.ignored_services: set = set()

    def receive(self, body: Dict[str, Any]):
        events = log_events(body)
        if not self.cfg.any_service:
            other = {e["service"] for e in events if e["service"] != SERVICE}
            for name in other - self.ignored_services:
                self.ignored_services.add(name)
                log(f"ignoring events from service.name={name or '(none)'}: only Cowork ({SERVICE}) is mapped")
            events = [e for e in events if e["service"] == SERVICE]
        self.mapper.add(events)

    def payload(self, p: Prompt, spans: List[Span]) -> Dict[str, Any]:
        res = [{"key": "project_name", "value": {"stringValue": self.cfg.project}},
               {"key": "service.name", "value": {"stringValue": p.service}}]
        if p.version:
            res.append({"key": "service.version", "value": {"stringValue": str(p.version)}})
        return {"resourceSpans": [{"resource": {"attributes": res},
                                   "scopeSpans": [{"scope": SCOPE, "spans": [s.otlp() for s in spans]}]}]}

    def send(self, payload: Dict[str, Any]) -> int:
        req = urllib.request.Request(self.cfg.endpoint, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Api-Key": self.cfg.api_key,
                                              "X-Secret-Key": self.cfg.secret_key})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                if e.code < 500 or attempt:
                    log(f"export failed: HTTP {e.code}")
                    return e.code
            except OSError as e:
                if attempt:
                    log(f"export failed: {e}")
                    return 0
            time.sleep(1)
        return 0

    def flush(self, force: bool = False):
        for p in self.mapper.due(force):
            spans = self.mapper.spans(p)
            status = self.send(self.payload(p, spans))
            log(f"prompt trace_id={p.trace_id} session.id={p.root.attrs.get('session.id')} "
                f"spans={len(spans)} http={status}")

    def loop(self):
        while not self.stop.wait(1.0):
            self.flush()


def log(msg: str):
    print(f"[fi-cowork-bridge] {msg}", file=sys.stderr, flush=True)


def decode_protobuf(raw: bytes) -> Optional[Dict[str, Any]]:
    try:
        from google.protobuf.json_format import MessageToDict
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    except ImportError:
        return None
    msg = ExportLogsServiceRequest()
    msg.ParseFromString(raw)
    return MessageToDict(msg)


class BodyError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def gunzip(raw: bytes) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(raw, MAX_BODY + 1)
    except zlib.error:
        raise BodyError(400, "could not decode the gzip body") from None
    if len(out) > MAX_BODY or d.unconsumed_tail:
        raise BodyError(413, f"body over {MAX_BODY} bytes after gzip decoding")
    if not d.eof:
        raise BodyError(400, "truncated gzip body")
    return out


def make_handler(bridge: Bridge):
    token = bridge.cfg.token
    last_logged: Dict[int, float] = {}

    class Handler(BaseHTTPRequestHandler):
        timeout = READ_TIMEOUT  # socket timeout: a stalled client cannot hold a thread

        def do_POST(self):  # noqa: N802
            # Nothing is read from the body before the token and path are checked.
            # Compared as bytes: compare_digest raises on non-ASCII str, which a client controls.
            sent = self.headers.get("Authorization", "").encode("utf-8", "replace")
            if token and not hmac.compare_digest(sent, ("Bearer " + token).encode("utf-8")):
                return self.reject(401, "missing or wrong bearer token")
            if self.path.split("?")[0].rstrip("/") not in ("", "/v1/logs"):
                return self.reject(404, "this bridge accepts OTLP logs on /v1/logs; enter the bare host as the "
                                        "endpoint, the exporter adds /v1/logs")
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            if ctype not in ("application/json", "application/x-protobuf"):
                return self.reject(415, f"unsupported content type {ctype or '(none)'}")
            try:
                raw = self.read_body()
            except BodyError as e:
                return self.reject(e.code, e.message)
            except OSError:  # timeout or reset while reading
                self.close_connection = True
                return log("dropped a request: the client stopped sending its body")
            try:
                if ctype == "application/json":
                    body = json.loads(raw or b"{}")
                else:
                    body = decode_protobuf(raw)
                    if body is None:
                        return self.reject(415, "choose HTTP/JSON in the Cowork admin form, "
                                                "or install opentelemetry-proto")
                bridge.receive(body)
            except Exception as e:  # noqa: BLE001  a bad batch must not stop the bridge
                log(f"dropped a batch: {type(e).__name__}")
                return self.reply(400, {"message": "could not parse OTLP logs"})
            self.reply(200, {})

        def read_body(self) -> bytes:
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                raw = self.read_chunked()
            else:
                length = self.headers.get("Content-Length")
                if length is None:
                    raise BodyError(411, "Content-Length or chunked transfer encoding required")
                n = to_int(length.strip())
                if n is None or n < 0:
                    raise BodyError(400, "bad Content-Length")
                if n > MAX_BODY:
                    raise BodyError(413, f"body over {MAX_BODY} bytes")
                raw = self.rfile.read(n)
                if len(raw) < n:
                    raise BodyError(400, "body shorter than Content-Length")
            encoding = (self.headers.get("Content-Encoding") or "identity").strip().lower()
            if encoding == "gzip":
                return gunzip(raw)
            if encoding not in ("identity", ""):
                raise BodyError(415, f"unsupported content encoding {encoding}")
            return raw

        def read_chunked(self) -> bytes:
            out = bytearray()
            while True:
                line = self.rfile.readline(1024)
                size = to_int_hex(line.split(b";")[0].strip())
                if size is None or size < 0:
                    raise BodyError(400, "bad chunked body")
                if size == 0:
                    while self.rfile.readline(1024) not in (b"\r\n", b"\n", b""):
                        pass  # trailers
                    return bytes(out)
                if len(out) + size > MAX_BODY:
                    raise BodyError(413, f"body over {MAX_BODY} bytes")
                chunk = self.rfile.read(size)
                if len(chunk) < size:
                    raise BodyError(400, "truncated chunked body")
                out += chunk
                self.rfile.readline(1024)  # CRLF after the chunk

        def reject(self, code: int, message: str):
            now = time.monotonic()
            if now - last_logged.get(code, -60.0) >= 60:  # one line per status per minute
                last_logged[code] = now
                log(f"rejected a request: HTTP {code} {message}")
            self.close_connection = True
            self.reply(code, {"message": message})

        def reply(self, code: int, obj: Dict[str, Any]):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    return Handler


def to_int_hex(v: bytes) -> Optional[int]:
    try:
        return int(v, 16)
    except ValueError:
        return None


def main() -> int:
    cfg = Config()
    if not (cfg.api_key and cfg.secret_key):
        log("FI_API_KEY and FI_SECRET_KEY are required")
        return 2
    host, port = cfg.listen.rsplit(":", 1)
    if not cfg.token and not cfg.allow_no_token:
        log("FI_BRIDGE_TOKEN is required, also behind a reverse proxy "
            "(FI_BRIDGE_ALLOW_NO_TOKEN=1 skips it, for local tests only)")
        return 2
    if not cfg.token and host not in LOOPBACK:
        log(f"WARNING: no FI_BRIDGE_TOKEN and listening on {host}: anyone who reaches this port can write "
            "traces into your project")
    bridge = Bridge(cfg)
    server = ThreadingHTTPServer((host, int(port)), make_handler(bridge))
    sender = threading.Thread(target=bridge.loop, daemon=True)
    sender.start()

    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log(f"listening on http://{cfg.listen}/v1/logs -> {cfg.endpoint} (project {cfg.project}, "
        f"content {'on' if cfg.capture else 'off'}, token {'on' if cfg.token else 'off'})")
    server.serve_forever()
    bridge.stop.set()
    sender.join(timeout=30)  # let a send in progress finish, then send what is left
    bridge.flush(force=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
