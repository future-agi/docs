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
response text, tool_input and tool_parameters, tool error text, user.email,
workspace.host_paths, enduser.id and process.owner are never forwarded unless
listed as content below, even when the admin's device config exports them.
FI_BRIDGE_CAPTURE_CONTENT=1 keeps the prompt, the response and tool_input;
user.email, workspace.host_paths, enduser.id and process.owner are never sent.

Stdlib only, Python 3.9+. Accepts OTLP/HTTP JSON (choose HTTP/JSON in the
admin form); HTTP/protobuf works when opentelemetry-proto is installed.

Environment:
    FI_API_KEY, FI_SECRET_KEY   Future AGI keys (required)
    FI_PROJECT_NAME             project (default: claude-cowork)
    FI_BASE_URL                 default https://api.futureagi.com; traces go to $FI_BASE_URL/tracer/v1/traces
    FI_OTLP_ENDPOINT            full traces URL, overrides FI_BASE_URL
    FI_BRIDGE_LISTEN            host:port to listen on (default 127.0.0.1:4320)
    FI_BRIDGE_TOKEN             shared secret; requests must send "Authorization: Bearer <token>".
                                Required when FI_BRIDGE_LISTEN is not a loopback address.
    FI_BRIDGE_IDLE_SECONDS      a prompt is sent this long after its last event (default 10)
    FI_BRIDGE_CAPTURE_CONTENT   1 = keep prompt, response and tool_input text
    FI_BRIDGE_MAX_CONTENT_CHARS per-field cap when content is on (default 4096)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

SCOPE = {"name": "fi-cowork-bridge", "version": "1.0.0"}
EVENTS = ("user_prompt", "assistant_response", "api_request", "api_error", "tool_result", "tool_decision")
REDACTED = ("<REDACTED>", "[REDACTED]", "")
LOOPBACK = ("127.0.0.1", "localhost", "::1")


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
        self.idle = float(e.get("FI_BRIDGE_IDLE_SECONDS") or 10)
        self.capture = e.get("FI_BRIDGE_CAPTURE_CONTENT", "").strip().lower() in ("1", "true", "yes", "on")
        self.max_chars = int(e.get("FI_BRIDGE_MAX_CONTENT_CHARS") or 4096)


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
        if int(record.get(k) or 0):
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
                                   "resource": resource, "seq": int(attrs.get("event.sequence") or 0)})
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


class Span:
    def __init__(self, trace_id: str, span_id: str, parent: Optional[str], name: str, kind: str, start: int, end: int):
        self.trace_id, self.span_id, self.parent, self.name = trace_id, span_id, parent, name
        self.start, self.end = start, end
        self.attrs: Dict[str, Any] = {"fi.span.kind": kind}
        self.error: Optional[str] = None
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
        self.last_event = time.monotonic()
        self.dirty = True
        self.version: Optional[str] = None

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
                p.version = ev["resource"].get("service.version") or p.version
                self.metadata(p.root, a, ev["resource"])
                getattr(self, name)(p, a, t)
                p.touch(t)

    def metadata(self, root: Span, a: Dict[str, Any], res: Dict[str, Any]):
        """Allow-listed identifiers. Never: user.email, workspace.host_paths, enduser.id, process.owner."""
        for src, dst in (("session.id", "session.id"), ("user.account_uuid", "user.id"),
                         ("organization.id", "cowork.organization_id"), ("terminal.type", "cowork.terminal_type")):
            if a.get(src) and dst not in root.attrs:
                root.attrs[dst] = a[src]
        if res.get("service.name") and "cowork.service_name" not in root.attrs:
            root.attrs["cowork.service_name"] = res["service.name"]

    def user_prompt(self, p: Prompt, a: Dict[str, Any], t: int):
        p.root.start = t if not p.root.sent else p.root.start
        p.root.attrs.update({"cowork.prompt_length": to_int(a.get("prompt_length")),
                             "input.value": self.content(a.get("prompt"))})

    def assistant_response(self, p: Prompt, a: Dict[str, Any], t: int):
        p.root.attrs.update({"gen_ai.request.model": a.get("model"),
                             "cowork.response_length": to_int(a.get("response_length")),
                             "output.value": self.content(a.get("response"))})

    def llm_span(self, p: Prompt, a: Dict[str, Any], t: int) -> Span:
        dur = to_int(a.get("duration_ms")) or 0
        span = Span(p.trace_id, hexid("llm", p.trace_id, a.get("event.sequence"), t), p.root.span_id,
                    "Cowork model request", "LLM", t - dur * 1_000_000, t)
        span.attrs.update({"gen_ai.request.model": a.get("model"), "gen_ai.system": "anthropic",
                           "cowork.speed": a.get("speed"), "cowork.attempt": to_int(a.get("attempt"))})
        p.children.append(span)
        p.root.attrs.setdefault("gen_ai.request.model", a.get("model"))
        return span

    def api_request(self, p: Prompt, a: Dict[str, Any], t: int):
        span = self.llm_span(p, a, t)
        inp, out = to_int(a.get("input_tokens")), to_int(a.get("output_tokens"))
        cr, cc = to_int(a.get("cache_read_tokens")), to_int(a.get("cache_creation_tokens"))
        total_in = None if inp is None else inp + (cr or 0) + (cc or 0)  # Anthropic reports cache separately
        span.attrs.update({"gen_ai.usage.input_tokens": total_in, "gen_ai.usage.output_tokens": out,
                           "gen_ai.usage.cache_read.input_tokens": cr,
                           "gen_ai.usage.cache_creation.input_tokens": cc,
                           "gen_ai.cost.total": to_float(a.get("cost_usd"))})
        # Prompt totals under cowork.* keys: gen_ai.usage.* on the prompt span
        # would be counted a second time in the trace's token total.
        for key, val in (("cowork.prompt.input_tokens", total_in), ("cowork.prompt.output_tokens", out)):
            p.root.attrs[key] = (p.root.attrs.get(key) or 0) + (val or 0)

    def api_error(self, p: Prompt, a: Dict[str, Any], t: int):
        span = self.llm_span(p, a, t)
        span.attrs["http.response.status_code"] = to_int(a.get("status_code"))
        # The API's error message (rate limit, overloaded), not user content.
        span.error = str(a.get("error") or f"HTTP {a.get('status_code')}")[:512]
        p.root.error = p.root.error or "model request failed"

    def tool_decision(self, p: Prompt, a: Dict[str, Any], t: int):
        p.decisions.append({"tool_name": a.get("tool_name"), "decision": a.get("decision"),
                            "source": a.get("source"), "time": t})

    def tool_result(self, p: Prompt, a: Dict[str, Any], t: int):
        dur = to_int(a.get("duration_ms")) or 0
        name = str(a.get("tool_name") or "tool")
        span = Span(p.trace_id, hexid("tool", p.trace_id, a.get("event.sequence"), name, t), p.root.span_id,
                    name, "TOOL", t - dur * 1_000_000, t)
        span.attrs.update({
            "gen_ai.tool.name": name,
            "cowork.success": a.get("success"),
            "cowork.decision": a.get("decision_type"),
            "cowork.decision_source": a.get("decision_source"),
            "cowork.tool_result_size_bytes": to_int(a.get("tool_result_size_bytes")),
            "cowork.mcp_server_scope": a.get("mcp_server_scope"),
            "input.value": self.content(a.get("tool_input")),
        })
        for d in p.decisions:  # the decision event for this call, oldest first
            if d["tool_name"] == name and d["time"] <= t:
                p.decisions.remove(d)
                break
        if str(a.get("success")).lower() == "false":
            span.error = self.content(a.get("error")) or "tool failed"
        p.children.append(span)
        p.root.attrs["cowork.tool_calls"] = sum(1 for c in p.children if c.attrs["fi.span.kind"] == "TOOL")

    def rejected(self, p: Prompt):
        """Rejected tool calls have a tool_decision and no tool_result."""
        for d in p.decisions:
            if d["decision"] == "reject":
                span = Span(p.trace_id, hexid("decision", p.trace_id, d["tool_name"], d["time"]), p.root.span_id,
                            str(d["tool_name"] or "tool"), "TOOL", d["time"], d["time"])
                span.attrs.update({"gen_ai.tool.name": d["tool_name"], "cowork.decision": "reject",
                                   "cowork.decision_source": d["source"]})
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
            out = [p.root] + [c for c in p.children if not c.sent]
            for s in out:
                s.sent = True
            p.dirty = False
            return out


# ---------------------------------------------------------------- export

class Bridge:
    def __init__(self, cfg: Config):
        self.cfg, self.mapper = cfg, CoworkMapper(cfg)
        self.stop = threading.Event()

    def receive(self, body: Dict[str, Any]):
        self.mapper.add(log_events(body))

    def payload(self, p: Prompt, spans: List[Span]) -> Dict[str, Any]:
        res = [{"key": "project_name", "value": {"stringValue": self.cfg.project}},
               {"key": "service.name", "value": {"stringValue": "cowork"}}]
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


def make_handler(bridge: Bridge):
    token = bridge.cfg.token

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if token and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                return self.reply(401, {"message": "missing or wrong bearer token"})
            if self.path.split("?")[0].rstrip("/") not in ("", "/v1/logs"):
                return self.reply(404, {"message": "this bridge accepts OTLP logs on /v1/logs only"})
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            try:
                if ctype == "application/json":
                    body = json.loads(raw or b"{}")
                elif ctype == "application/x-protobuf":
                    body = decode_protobuf(raw)
                    if body is None:
                        return self.reply(415, {"message": "choose HTTP/JSON in the Cowork admin form, "
                                                           "or install opentelemetry-proto"})
                else:
                    return self.reply(415, {"message": f"unsupported content type {ctype}"})
                bridge.receive(body)
            except Exception as e:  # noqa: BLE001  a bad batch must not stop the bridge
                log(f"dropped a batch: {type(e).__name__}")
                return self.reply(400, {"message": "could not parse OTLP logs"})
            self.reply(200, {})

        def reply(self, code: int, obj: Dict[str, Any]):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    return Handler


def main() -> int:
    cfg = Config()
    if not (cfg.api_key and cfg.secret_key):
        log("FI_API_KEY and FI_SECRET_KEY are required")
        return 2
    host, port = cfg.listen.rsplit(":", 1)
    if host not in LOOPBACK and not cfg.token:
        log("FI_BRIDGE_TOKEN is required when listening on a non-loopback address")
        return 2
    bridge = Bridge(cfg)
    server = ThreadingHTTPServer((host, int(port)), make_handler(bridge))
    threading.Thread(target=bridge.loop, daemon=True).start()

    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log(f"listening on http://{cfg.listen}/v1/logs -> {cfg.endpoint} (project {cfg.project}, "
        f"content {'on' if cfg.capture else 'off'}, token {'on' if cfg.token else 'off'})")
    server.serve_forever()
    bridge.stop.set()
    bridge.flush(force=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
