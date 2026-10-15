#!/usr/bin/env python3
"""Codex OpenTelemetry log events -> Future AGI traces.

Codex's [otel] exporter sends log events (codex.user_prompt, codex.api_request,
codex.sse_event, codex.tool_decision, codex.tool_result, ...). The Future AGI
collector ingests traces only, so this bridge listens for those OTLP/HTTP log
exports and turns each Codex turn into one trace:

    Codex turn (agent)                 one user prompt, session.id = conversation.id
    |-- Codex model request (llm)      codex.api_request + its response.completed tokens
    |-- exec (tool)                    codex.tool_result (+ codex.tool_decision)
    |   `-- exec_command (tool)        a call made inside a code-mode `exec` call
    `-- Codex model request (llm)

Stdlib only, Python 3.9+. Codex must send OTLP/JSON (protocol = "json").
Prompt text, tool arguments, and tool output are dropped unless
FI_BRIDGE_CAPTURE_CONTENT=1.

    FI_API_KEY=... FI_SECRET_KEY=... python3 bridge.py

Environment:
    FI_API_KEY, FI_SECRET_KEY   Future AGI keys (required)
    FI_PROJECT_NAME             project (default: codex)
    FI_BASE_URL                 default https://api.futureagi.com; traces go to $FI_BASE_URL/tracer/v1/traces
    FI_OTLP_ENDPOINT            full traces URL, overrides FI_BASE_URL
    FI_BRIDGE_LISTEN            host:port Codex sends logs to (default 127.0.0.1:4319)
    FI_BRIDGE_IDLE_SECONDS      a turn is sent this long after its last event (default 10)
    FI_BRIDGE_CAPTURE_CONTENT   1 = keep prompt text, tool arguments and tool output
    FI_BRIDGE_MAX_CONTENT_CHARS per-field cap when content is on (default 4096)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

SCOPE = {"name": "fi-codex-bridge", "version": "1.0.0"}
AGENT, LLM, TOOL = "AGENT", "LLM", "TOOL"
STATUS_ERROR = 2
REDACTED = ("[REDACTED]", "<REDACTED>", "")
STREAM_END = ("response.completed", "response.failed", "error")
# Events that belong to a turn. codex.websocket_request is the WebSocket
# transport's counterpart of codex.api_request (not tested; see the docs page).
TURN_EVENTS = ("codex.api_request", "codex.websocket_request", "codex.sse_event", "codex.tool_decision",
               "codex.tool_result", "codex.turn_ttft", "codex.turn_cost")
# Code-mode: the model's `exec` tool runs further tool calls inside itself;
# in 0.162.1 those inner calls have call ids starting with "exec-".
CODE_MODE_TOOL, CODE_MODE_CALL_PREFIX = "exec", "exec-"
# An error code token from a provider's JSON error body ("code" wins over "type").
ERROR_CODE = [re.compile(r'"%s"\s*:\s*"([A-Za-z0-9_.-]{1,64})"' % k) for k in ("code", "type")]


class Config:
    def __init__(self, environ: Optional[Dict[str, str]] = None):
        e = dict(os.environ if environ is None else environ)
        self.api_key = e.get("FI_API_KEY", "")
        self.secret_key = e.get("FI_SECRET_KEY", "")
        self.project = e.get("FI_PROJECT_NAME") or "codex"
        base = (e.get("FI_BASE_URL") or "https://api.futureagi.com").rstrip("/")
        self.endpoint = e.get("FI_OTLP_ENDPOINT") or base + "/tracer/v1/traces"
        self.listen = e.get("FI_BRIDGE_LISTEN") or "127.0.0.1:4319"
        self.idle = float(e.get("FI_BRIDGE_IDLE_SECONDS") or 10)
        self.capture = e.get("FI_BRIDGE_CAPTURE_CONTENT", "").strip().lower() in ("1", "true", "yes", "on")
        self.max_chars = int(e.get("FI_BRIDGE_MAX_CONTENT_CHARS") or 4096)


# ---------------------------------------------------------------- OTLP input

def any_value(v: Dict[str, Any]) -> Any:
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


def parse_time(attrs: Dict[str, Any], record: Dict[str, Any]) -> int:
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
    """Flatten an OTLP/JSON ExportLogsServiceRequest into Codex events."""
    events = []
    for rl in body.get("resourceLogs", []):
        resource = kv(rl.get("resource", {}).get("attributes"))
        for sl in rl.get("scopeLogs", []):
            for rec in sl.get("logRecords", []):
                attrs = kv(rec.get("attributes"))
                name = attrs.get("event.name") or rec.get("eventName") or ""
                if not str(name).startswith("codex."):
                    continue
                events.append({"name": name, "attrs": attrs, "time": parse_time(attrs, rec),
                               "resource": resource})
    events.sort(key=lambda e: e["time"])
    return events


# ---------------------------------------------------------------- mapping

def hexid(*parts: Any, size: int = 16) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[: size * 2]


def to_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class Span:
    def __init__(self, trace_id: str, span_id: str, parent: Optional[str], name: str, kind: str,
                 start: int, end: int):
        self.trace_id, self.span_id, self.parent = trace_id, span_id, parent
        self.name, self.kind, self.start, self.end = name, kind, start, end
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
                "startTimeUnixNano": str(self.start), "endTimeUnixNano": str(max(self.end, self.start)),
                "attributes": attrs}
        if self.parent:
            span["parentSpanId"] = self.parent
        if self.error is not None:
            span["status"] = {"code": STATUS_ERROR, "message": self.error}
        return span


def to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Turn:
    def __init__(self, conv: str, index: int, start: int):
        self.trace_id = hexid("codex-bridge", conv, index, start)
        self.root = Span(self.trace_id, hexid("root", self.trace_id, size=8), None, "Codex turn", AGENT,
                         start, start)
        self.children: List[Span] = []
        self.pending_llm: List[Span] = []
        self.decisions: Dict[str, Dict[str, Any]] = {}
        self.last_event = time.monotonic()
        self.dirty = True
        self.root.attrs.update({"session.id": conv, "codex.conversation_id": conv})

    def touch(self, t: int):
        self.root.end = max(self.root.end, t)
        self.last_event = time.monotonic()
        self.dirty = True


class CodexMapper:
    """Turns Codex log events into spans, one trace per user prompt."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.convs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def content(self, value: Any) -> Optional[str]:
        if not self.cfg.capture or value is None or value in REDACTED:
            return None
        s = str(value)
        return s if len(s) <= self.cfg.max_chars else s[: self.cfg.max_chars] + "...[truncated]"

    def conv(self, cid: str) -> Dict[str, Any]:
        return self.convs.setdefault(cid, {"turns": 0, "turn": None, "ctx": {}, "version": None, "seen": {}})

    def duplicate(self, st: Dict[str, Any], ev: Dict[str, Any]) -> bool:
        """OTLP export is at-least-once: skip an event already applied (same name, time, attributes)."""
        key = hashlib.sha256(json.dumps([ev["name"], ev["time"], ev["attrs"]], sort_keys=True,
                                        default=str).encode()).hexdigest()
        if key in st["seen"]:
            return True
        st["seen"][key] = None
        if len(st["seen"]) > 20000:
            st["seen"].pop(next(iter(st["seen"])))
        return False

    def turn_for(self, state: Dict[str, Any], cid: str, t: int) -> Turn:
        if state["turn"] is None:  # events before the first prompt
            state["turns"] += 1
            state["turn"] = Turn(cid, state["turns"], t)
            state["turn"].root.attrs["codex.turn.implicit"] = True
        return state["turn"]

    def add(self, events: List[Dict[str, Any]]) -> List[Turn]:
        """Apply events; return turns that a new prompt closed."""
        closed = []
        with self.lock:
            for ev in events:
                a, t = ev["attrs"], ev["time"]
                cid = str(a.get("conversation.id") or "unknown")
                st = self.conv(cid)
                st["version"] = a.get("app.version") or ev["resource"].get("service.version") or st["version"]
                st["service"] = ev["resource"].get("service.name") or st.get("service")
                name = ev["name"]
                acted = name in TURN_EVENTS or name in ("codex.conversation_starts", "codex.user_prompt")
                if not acted or (name == "codex.sse_event" and a.get("event.kind") not in STREAM_END):
                    continue  # startup phases and stream deltas
                if self.duplicate(st, ev):
                    continue
                if name == "codex.conversation_starts":
                    st["ctx"].update({k: a.get(k) for k in ("provider_name", "approval_policy", "sandbox_policy",
                                                          "reasoning_effort", "reasoning_summary")})
                    continue
                if name == "codex.user_prompt":
                    if st["turn"] is not None and st["turn"].dirty:
                        closed.append(st["turn"])
                    st["turns"] += 1
                    turn = st["turn"] = Turn(cid, st["turns"], t)
                    turn.root.attrs.update({"codex.prompt_length": to_int(a.get("prompt_length")),
                                            "input.value": self.content(a.get("prompt"))})
                    self.common(turn.root, a, st)
                    turn.touch(t)
                    continue
                turn = self.turn_for(st, cid, t)
                if name in ("codex.api_request", "codex.websocket_request"):
                    self.llm(turn, a, t, st)
                elif name == "codex.sse_event":
                    self.stream_event(turn, a, t)
                elif name == "codex.tool_decision":
                    turn.decisions[str(a.get("call_id"))] = a
                elif name == "codex.tool_result":
                    self.tool(turn, a, t)
                elif name == "codex.turn_ttft":
                    turn.root.attrs["codex.turn.ttft_ms"] = to_int(a.get("duration_ms"))
                elif name == "codex.turn_cost":  # added to the turn open when it arrives
                    turn.root.attrs["codex.turn.estimated_usd"] = to_float(a.get("usage.estimated_usd"))
                turn.touch(t)
        return closed

    def common(self, span: Span, a: Dict[str, Any], st: Dict[str, Any]):
        ctx = st["ctx"]
        span.attrs.update({
            "gen_ai.request.model": a.get("model"),
            "codex.originator": a.get("originator"),
            "codex.provider": ctx.get("provider_name"),
            "codex.approval_policy": ctx.get("approval_policy"),
            "codex.sandbox_policy": ctx.get("sandbox_policy"),
            "codex.reasoning_effort": ctx.get("reasoning_effort"),
            "codex.reasoning_summary": ctx.get("reasoning_summary"),
        })

    def llm(self, turn: Turn, a: Dict[str, Any], t: int, st: Dict[str, Any]):
        dur = to_int(a.get("duration_ms")) or 0
        n = len(turn.children)
        span = Span(turn.trace_id, hexid("llm", turn.trace_id, n, t, size=8), turn.root.span_id,
                    "Codex model request", LLM, t - dur * 1_000_000, t)
        status = to_int(a.get("http.response.status_code"))
        span.attrs.update({
            "gen_ai.request.model": a.get("model"),
            "gen_ai.system": (st["ctx"].get("provider_name") or "openai").lower(),
            "http.response.status_code": status,
            "codex.attempt": to_int(a.get("attempt")),
            "codex.endpoint": a.get("endpoint"),
            "codex.transport": "websocket" if "websocket" in str(a.get("event.name")) else "http",
        })
        err = a.get("error.message")
        if (status is not None and status >= 400) or err:
            span.error = self.error_summary(status, err)
        turn.children.append(span)
        turn.pending_llm.append(span)

    def error_summary(self, status: Optional[int], err: Any) -> str:
        """Provider and proxy error bodies are free text; without content capture
        only the HTTP status and an error code parsed from the body are kept."""
        if self.cfg.capture and err:
            return str(err)[:512]
        text = str(err or "")
        code = next((m.group(1) for m in (p.search(text) for p in ERROR_CODE) if m), None)
        return " ".join([f"HTTP {status}" if status else "request failed"] + ([code] if code else []))

    def stream_event(self, turn: Turn, a: Dict[str, Any], t: int):
        kind = a.get("event.kind")
        span = turn.pending_llm[-1] if turn.pending_llm else None
        if span is None:
            return
        span.end = max(span.end, t)
        span.sent = False  # already exported spans are sent again with the same id
        if kind != "response.completed":
            span.error = span.error or str(kind)
            return
        tokens = {
            "gen_ai.usage.input_tokens": to_int(a.get("input_token_count")),
            "gen_ai.usage.output_tokens": to_int(a.get("output_token_count")),
            "gen_ai.usage.cache_read.input_tokens": to_int(a.get("cached_token_count")),
            "codex.usage.reasoning_tokens": to_int(a.get("reasoning_token_count")),
            "codex.ttft_ms": to_int(a.get("ttft_ms")),
        }
        if tokens["gen_ai.usage.input_tokens"] is None:
            return  # Codex logs response.completed twice; only one carries the counts
        span.attrs.update(tokens)
        turn.pending_llm.remove(span)
        # Turn totals under codex.* keys: gen_ai.usage.* on the turn would be
        # counted a second time in the trace's token total.
        for key, total in (("gen_ai.usage.input_tokens", "codex.turn.input_tokens"),
                           ("gen_ai.usage.output_tokens", "codex.turn.output_tokens")):
            turn.root.attrs[total] = (turn.root.attrs.get(total) or 0) + (tokens[key] or 0)

    def tool(self, turn: Turn, a: Dict[str, Any], t: int):
        dur = to_int(a.get("duration_ms")) or 0
        call_id = str(a.get("call_id") or len(turn.children))
        name = str(a.get("tool_name") or "tool")
        span = Span(turn.trace_id, hexid("tool", turn.trace_id, call_id, t, size=8), turn.root.span_id,
                    name, TOOL, t - dur * 1_000_000, t)
        decision = turn.decisions.pop(call_id, {})
        span.attrs.update({
            "gen_ai.tool.name": name,
            "gen_ai.tool.call.id": call_id,
            "codex.tool_namespace": a.get("tool_namespace"),
            "codex.mcp_server": a.get("mcp_server") or None,
            "codex.success": a.get("success"),
            "codex.output_truncated": a.get("output_truncated"),
            "codex.decision": decision.get("decision"),
            "codex.decision_source": decision.get("source"),
            "input.value": self.content(a.get("arguments")),
            "output.value": self.content(a.get("output")),
        })
        if str(a.get("success")).lower() == "false":
            span.error = "tool call failed"
        turn.children.append(span)
        turn.root.attrs["codex.tool_calls"] = sum(1 for c in turn.children if c.kind == TOOL)

    def nest(self, turn: Turn):
        """Parent tool calls made inside a code-mode `exec` call to that call.

        Only `exec` calls are parents and only code-mode calls (call id
        "exec-...") are nested, so parallel sibling calls stay siblings.
        Every tool is re-checked on each flush; a span whose parent changes
        after it was sent is sent again under the same id."""
        tools = [c for c in turn.children if c.kind == TOOL]
        outers = [o for o in tools if o.name == CODE_MODE_TOOL]
        for inner in tools:
            if inner.name == CODE_MODE_TOOL:
                continue
            nested = str(inner.attrs.get("gen_ai.tool.call.id") or "").startswith(CODE_MODE_CALL_PREFIX)
            around = [o for o in outers if nested and o.start <= inner.start and inner.end <= o.end]
            parent = min(around, key=lambda o: o.end - o.start).span_id if around else turn.root.span_id
            if parent != inner.parent:
                inner.parent = parent
                inner.sent = False

    def due(self, force: bool = False) -> List[Turn]:
        """Turns with unsent changes whose last event is older than the idle window.

        A sent turn stays current: events that arrive later (a long tool call)
        go into the same trace, and the turn span is sent again with its new
        end time under the same span id."""
        out = []
        with self.lock:
            now = time.monotonic()
            for cid, st in list(self.convs.items()):
                turn = st["turn"]
                if turn is not None and turn.dirty and (force or now - turn.last_event >= self.cfg.idle):
                    out.append(turn)
                elif turn is not None and not turn.dirty and now - turn.last_event > 3600:
                    del self.convs[cid]
        return out

    def spans(self, turn: Turn) -> List[Span]:
        """The turn span plus the children not sent yet; marks them sent."""
        with self.lock:
            self.nest(turn)
            for c in turn.children:
                if not turn.root.sent:
                    turn.root.start = min(turn.root.start, c.start)
                turn.root.end = max(turn.root.end, c.end)
            # A failed request that Codex retried successfully stays ERROR on
            # its own span; the turn is ERROR only if its last request failed.
            llms = sorted((c for c in turn.children if c.kind == LLM), key=lambda c: c.start)
            turn.root.error = "model request failed" if llms and llms[-1].error else None
            out = [turn.root] + [c for c in turn.children if not c.sent]
            for s in out:
                s.sent = True
            turn.dirty = False
            return out


# ---------------------------------------------------------------- export

class Exporter:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def payload(self, spans: List[Span], version: Optional[str], service: Optional[str]) -> Dict[str, Any]:
        res = [{"key": "project_name", "value": {"stringValue": self.cfg.project}},
               {"key": "service.name", "value": {"stringValue": "codex"}}]
        if version:
            res.append({"key": "service.version", "value": {"stringValue": str(version)}})
        if service:
            res.append({"key": "codex.client", "value": {"stringValue": str(service)}})
        return {"resourceSpans": [{"resource": {"attributes": res},
                                   "scopeSpans": [{"scope": SCOPE, "spans": [s.otlp() for s in spans]}]}]}

    def send(self, payload: Dict[str, Any]) -> int:
        req = urllib.request.Request(self.cfg.endpoint, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "X-Api-Key": self.cfg.api_key,
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


class Bridge:
    def __init__(self, cfg: Config):
        self.cfg, self.mapper, self.exporter = cfg, CodexMapper(cfg), Exporter(cfg)
        self.stop = threading.Event()
        self.ready: List[Turn] = []  # turns a new prompt closed, sent by the next flush
        self.ready_lock = threading.Lock()

    def receive(self, body: Dict[str, Any]):
        """Apply a batch. No network I/O here, so Codex gets its ack at once."""
        closed = self.mapper.add(log_events(body))
        with self.ready_lock:
            self.ready.extend(closed)

    def export(self, turn: Turn):
        cid = turn.root.attrs["session.id"]
        st = self.mapper.convs.get(cid, {})
        spans = self.mapper.spans(turn)
        status = self.exporter.send(self.exporter.payload(spans, st.get("version"), st.get("service")))
        log(f"turn trace_id={turn.trace_id} session.id={cid} spans={len(spans)} http={status}")

    def flush(self, force: bool = False):
        with self.ready_lock:
            turns, self.ready = self.ready, []
        for turn in turns + [t for t in self.mapper.due(force) if t not in turns]:
            self.export(turn)

    def loop(self):
        while not self.stop.wait(1.0):
            self.flush()


def log(msg: str):
    print(f"[fi-codex-bridge] {msg}", file=sys.stderr, flush=True)


def decode_protobuf(raw: bytes) -> Optional[Dict[str, Any]]:
    try:
        from google.protobuf.json_format import MessageToDict
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    except ImportError:
        return None
    msg = ExportLogsServiceRequest()
    msg.ParseFromString(raw)
    return MessageToDict(msg)


_rejections: Dict[str, int] = {}


def log_rejection(reason: str):
    """One log line for the first rejection of each kind, then every 100th."""
    n = _rejections[reason] = _rejections.get(reason, 0) + 1
    if n == 1 or n % 100 == 0:
        log(f"rejected request ({n}x): {reason}")


def make_handler(bridge: Bridge):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            path = self.path.split("?")[0]
            if path != "/v1/logs":
                log_rejection(f"path {path}: Codex's exporter endpoint must end in /v1/logs")
                return self.reply(404, {"message": "this bridge accepts /v1/logs only"})
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            try:
                if ctype == "application/json":
                    body = json.loads(raw or b"{}")
                elif ctype == "application/x-protobuf":
                    body = decode_protobuf(raw)
                    if body is None:
                        log_rejection('application/x-protobuf: set protocol = "json" in the [otel] exporter')
                        return self.reply(415, {"message": "set protocol = \"json\" in Codex's [otel] exporter"})
                else:
                    log_rejection(f"content type {ctype or 'none'}")
                    return self.reply(415, {"message": f"unsupported content type {ctype}"})
                bridge.receive(body)
            except Exception as e:  # noqa: BLE001  a bad batch must not stop the bridge
                log(f"dropped a batch: {type(e).__name__}: {e}")
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
    bridge = Bridge(cfg)
    host, port = cfg.listen.rsplit(":", 1)
    server = ThreadingHTTPServer((host, int(port)), make_handler(bridge))
    threading.Thread(target=bridge.loop, daemon=True).start()

    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log(f"listening on http://{cfg.listen}/v1/logs -> {cfg.endpoint} (project {cfg.project}, "
        f"content {'on' if cfg.capture else 'off'})")
    server.serve_forever()
    bridge.stop.set()
    bridge.flush(force=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
