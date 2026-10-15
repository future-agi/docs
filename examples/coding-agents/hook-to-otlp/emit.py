#!/usr/bin/env python3
"""Coding-agent hook -> OTLP/HTTP spans for Future AGI.

Usage (as a hook command):

    python3 emit.py <app> [<event>] [--env-file PATH] < payload.json

``<app>`` selects ``adapters/<app>.py``. ``<event>`` is the hook name when
the host does not put it in the payload. The script reads one JSON object
from stdin, prints what the host expects on stdout, and always exits 0.

One agent session becomes one trace (the trace id is derived from the
session id). Turns, tools, subagents, and model responses become child
spans. Start/end hooks are paired through a small per-session state file.

Privacy: prompts, tool arguments, tool results, model text, and error text
are dropped unless FI_HOOK_CAPTURE_CONTENT=1. Standard library only,
Python 3.9+.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import re
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from adapters.base import (  # noqa: E402
    END, ERROR, EVENT, INSTANT, LLM, OK, SESSION, START, SUBAGENT, TOOL, TURN,
    UPDATE, SpanEvent,
)

VERSION = "0.1.0"
SCOPE_NAME = "fi-hook-to-otlp"
DEFAULT_BASE_URL = "https://api.futureagi.com"
TRACES_PATH = "/tracer/v1/traces"
DEFAULT_ENV_FILE = Path("~/.config/fi-hook-to-otlp/env")

DEFAULT_KIND = {
    SESSION: "AGENT", TURN: "CHAIN", TOOL: "TOOL",
    SUBAGENT: "AGENT", LLM: "LLM", EVENT: "CHAIN",
}
OTLP_STATUS = {None: 0, OK: 1, ERROR: 2}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b((?:api[_-]?key|secret[_-]?key|access[_-]?token|password|passwd|token)\b[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"),
)
MAX_ENDED_TURNS = 64


@dataclass
class Config:
    app: str
    endpoint: str
    api_key: str
    secret_key: str
    project_name: str
    capture_content: bool
    max_content_chars: int
    timeout: float
    sync: bool
    state_dir: Path
    state_ttl_s: float
    log_file: Optional[str]
    dump_file: Optional[str]
    disabled: bool

    @classmethod
    def from_env(cls, app: str, env: Mapping[str, str]) -> "Config":
        base = env.get("FI_BASE_URL") or DEFAULT_BASE_URL
        endpoint = env.get("FI_OTLP_ENDPOINT") or base.rstrip("/") + TRACES_PATH
        state_root = env.get("FI_HOOK_STATE_DIR") or os.path.join(
            tempfile.gettempdir(), f"fi-hook-to-otlp-{_uid()}")
        return cls(
            app=app,
            endpoint=endpoint,
            api_key=env.get("FI_API_KEY", ""),
            secret_key=env.get("FI_SECRET_KEY", ""),
            project_name=env.get("FI_PROJECT_NAME") or app,
            capture_content=_truthy(env.get("FI_HOOK_CAPTURE_CONTENT")),
            max_content_chars=_int(env.get("FI_HOOK_MAX_CONTENT_CHARS"), 4096),
            timeout=_float(env.get("FI_HOOK_TIMEOUT"), 3.0),
            sync=_truthy(env.get("FI_HOOK_SYNC")),
            state_dir=Path(state_root) / app,
            state_ttl_s=_float(env.get("FI_HOOK_STATE_TTL_HOURS"), 24.0) * 3600,
            log_file=env.get("FI_HOOK_LOG_FILE") or None,
            dump_file=env.get("FI_HOOK_DUMP_FILE") or None,
            disabled=_truthy(env.get("FI_HOOK_DISABLED")),
        )

    @property
    def can_export(self) -> bool:
        return bool(self.api_key and self.secret_key and not self.disabled)


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value else default
    except ValueError:
        return default


def _float(value: Optional[str], default: float) -> float:
    try:
        return float(value) if value else default
    except ValueError:
        return default


def _uid() -> str:
    getuid = getattr(os, "getuid", None)
    return str(getuid()) if getuid else os.environ.get("USERNAME", "user")


# ---------------------------------------------------------------- ids


def _hex(*parts: str, length: int) -> str:
    raw = "\x1f".join(parts).encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:length]


def trace_id(app: str, session_id: str) -> str:
    """Deterministic 32-hex OTLP trace id: one session, one trace."""
    return _hex("trace", app, session_id, length=32)


def span_id(app: str, session_id: str, scope: str, key: str) -> str:
    """Deterministic 16-hex span id for (session, scope, key)."""
    return _hex("span", app, session_id, scope, key, length=16)


# ---------------------------------------------------------------- content


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def render_content(value: Any, max_chars: int) -> Optional[str]:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = redact(text)
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars] + f"...[truncated {len(text) - max_chars} chars]"
    return text


# ---------------------------------------------------------------- state


@contextlib.contextmanager
def session_state(cfg: Config, session_id: str) -> Iterator[Dict[str, Any]]:
    """Lock and load the per-session state file; save it on exit.

    The state dir is created 0700. If the yielded dict gets ``_delete`` set,
    the file is removed instead of saved.
    """
    cfg.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = cfg.state_dir / (_hex("state", cfg.app, session_id, length=32) + ".json")
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as handle:
        _lock(handle)
        try:
            raw = handle.read()
            try:
                state = json.loads(raw) if raw.strip() else {}
            except ValueError:
                state = {}
            if not isinstance(state, dict):
                state = {}
            yield state
            if state.pop("_delete", False):
                os.unlink(str(path))
            else:
                handle.seek(0)
                handle.truncate()
                handle.write(json.dumps(state, separators=(",", ":")))
                handle.flush()
        finally:
            _unlock(handle)


def _lock(handle: Any) -> None:
    try:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except ImportError:  # Windows: best effort, no lock
        pass


def _unlock(handle: Any) -> None:
    try:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except ImportError:
        pass


def sweep_state(cfg: Config, now_s: Optional[float] = None) -> None:
    """Remove state files untouched for longer than FI_HOOK_STATE_TTL_HOURS."""
    now_s = time.time() if now_s is None else now_s
    try:
        for entry in cfg.state_dir.glob("*.json"):
            with contextlib.suppress(OSError):
                if now_s - entry.stat().st_mtime > cfg.state_ttl_s:
                    entry.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------- spans


class SpanBuilder:
    """Applies SpanEvents to one session's state and collects finished spans."""

    def __init__(self, cfg: Config, adapter: Any, state: Dict[str, Any], session_id: str, now_ns: int):
        self.cfg = cfg
        self.adapter = adapter
        self.state = state
        self.sid = session_id
        self.now = now_ns
        self.spans: List[Dict[str, Any]] = []
        state.setdefault("open", {})
        state.setdefault("ended_turns", [])
        state.setdefault("session", {})
        self.trace = trace_id(cfg.app, session_id)
        self.root = span_id(cfg.app, session_id, SESSION, "")

    # -- helpers

    def _start_of(self, ev: SpanEvent) -> int:
        if ev.phase in (END, INSTANT) and ev.duration_ms and ev.duration_ms > 0:
            return self.now - int(ev.duration_ms * 1_000_000)
        return self.now

    def _ensure_session(self, start_ns: int) -> Dict[str, Any]:
        session = self.state["session"]
        if "start_ns" not in session:
            session["start_ns"] = start_ns
        elif not session.get("exported") and start_ns < session["start_ns"]:
            session["start_ns"] = start_ns
        return session

    def _turn_key(self, ev: SpanEvent) -> Optional[str]:
        if ev.scope == TURN:
            return ev.key or None
        return ev.turn_id or self.state.get("current_turn")

    def _ensure_turn(self, key: str, start_ns: int) -> Optional[Dict[str, Any]]:
        """Open turn record for ``key`` (auto-opened on first sight)."""
        if key in self.state["ended_turns"]:
            return None
        slot = f"{TURN}:{key}"
        rec = self.state["open"].get(slot)
        if rec is None:
            rec = self.state["open"][slot] = {
                "scope": TURN, "key": key, "start_ns": start_ns, "attrs": {},
                "parent": self.root,
            }
            self.state["current_turn"] = key
        elif start_ns < rec["start_ns"]:
            rec["start_ns"] = start_ns
        return rec

    def _parent_for(self, ev: SpanEvent, start_ns: int) -> Tuple[str, Optional[str]]:
        if ev.scope == SESSION:
            return "", None
        if ev.scope == TURN:
            return self.root, ev.key or None
        turn = self._turn_key(ev)
        if turn:
            self._ensure_turn(turn, start_ns)
            return span_id(self.cfg.app, self.sid, TURN, turn), turn
        return self.root, None

    def _merge(self, rec: Dict[str, Any], ev: SpanEvent) -> None:
        rec.setdefault("attrs", {}).update(ev.attributes or {})
        for field in ("name", "kind", "model", "status", "status_message"):
            value = getattr(ev, field)
            if value is not None:
                rec[field] = value
        if self.cfg.capture_content:
            for field in ("input", "output", "error_message"):
                value = getattr(ev, field)
                if value is not None:
                    rec[field] = render_content(value, self.cfg.max_content_chars)

    def _default_name(self, scope: str, rec: Dict[str, Any]) -> str:
        display = getattr(self.adapter, "DISPLAY_NAME", self.cfg.app)
        if scope == SESSION:
            return f"{display} session"
        if scope == TURN:
            return f"{display} turn"
        if scope == TOOL:
            return "tool"
        return scope

    def _emit(self, scope: str, sid: str, parent: str, start_ns: int, end_ns: int,
              rec: Dict[str, Any], event: str, turn: Optional[str]) -> None:
        attrs: Dict[str, Any] = dict(rec.get("attrs") or {})
        kind = rec.get("kind") or DEFAULT_KIND.get(scope, "UNKNOWN")
        name = rec.get("name") or self._default_name(scope, rec)
        attrs.update({
            "fi.span.kind": kind,
            "session.id": self.sid,
            "gen_ai.conversation.id": self.sid,
            "coding_agent.app": self.cfg.app,
            "coding_agent.scope": scope,
            "coding_agent.hook.event": event,
        })
        if turn:
            attrs["coding_agent.turn.id"] = turn
        if scope == TOOL:
            attrs.setdefault("gen_ai.tool.name", name)
            if rec.get("key") and not rec.get("synthetic_key"):
                attrs.setdefault("gen_ai.tool.call.id", rec["key"])
        model = rec.get("model")
        if model and scope in (SESSION, TURN, LLM, SUBAGENT):
            attrs["llm.model_name"] = model
            attrs["gen_ai.request.model"] = model
        if rec.get("incomplete"):
            attrs["coding_agent.incomplete"] = True
        status = rec.get("status")
        message = rec.get("status_message")
        if self.cfg.capture_content:
            if rec.get("input") is not None:
                attrs["input.value"] = rec["input"]
            if rec.get("output") is not None:
                attrs["output.value"] = rec["output"]
            if rec.get("error_message") is not None:
                attrs["exception.message"] = rec["error_message"]
                message = rec["error_message"]
        span: Dict[str, Any] = {
            "traceId": self.trace,
            "spanId": sid,
            "name": str(name),
            "kind": 1,
            "startTimeUnixNano": str(start_ns),
            "endTimeUnixNano": str(max(end_ns, start_ns)),
            "attributes": otlp_attributes(attrs),
            "status": {"code": OTLP_STATUS.get(status, 0)},
        }
        if parent:
            span["parentSpanId"] = parent
        if status == ERROR and message:
            span["status"]["message"] = str(message)[:512]
        self.spans.append(span)

    def _emit_root(self, event: str) -> None:
        session = self.state["session"]
        rec = dict(session)
        rec.setdefault("attrs", {})
        if not rec.get("model") and self.state.get("model"):
            rec["model"] = self.state["model"]
        self._emit(SESSION, self.root, "", session["start_ns"], self.now, rec, event, None)
        session["exported"] = True

    def _close_children(self, turn: Optional[str], event: str) -> None:
        """Export still-open spans under ``turn`` (or all) as incomplete."""
        for slot, rec in list(self.state["open"].items()):
            if rec["scope"] == TURN:
                continue
            if turn is not None and rec.get("turn") != turn:
                continue
            del self.state["open"][slot]
            rec["incomplete"] = True
            sid = span_id(self.cfg.app, self.sid, rec["scope"], rec["key"])
            self._emit(rec["scope"], sid, rec["parent"], rec["start_ns"], self.now, rec, event, rec.get("turn"))

    def _end_turn(self, key: str, rec: Dict[str, Any], event: str) -> None:
        self._close_children(key, event)
        sid = span_id(self.cfg.app, self.sid, TURN, key)
        self._emit(TURN, sid, self.root, rec["start_ns"], self.now, rec, event, key)
        ended = self.state["ended_turns"]
        ended.append(key)
        del ended[:-MAX_ENDED_TURNS]
        if self.state.get("current_turn") == key:
            self.state["current_turn"] = None

    # -- main entry

    def apply(self, ev: SpanEvent, event: str) -> None:
        start_ns = self._start_of(ev)
        session = self._ensure_session(start_ns)
        if ev.model:
            self.state["model"] = ev.model
        parent, turn = self._parent_for(ev, start_ns)
        if turn:
            turn_rec = self.state["open"].get(f"{TURN}:{turn}")
            if turn_rec is not None and ev.model:
                turn_rec["model"] = ev.model

        if ev.scope == SESSION:
            self._apply_session(ev, event, session)
            return
        if ev.scope == TURN:
            self._apply_turn(ev, event, start_ns)
            return

        key = ev.key
        synthetic = False
        if not key:
            key, synthetic = secrets.token_hex(8), True
        slot = f"{ev.scope}:{key}"
        if ev.phase == START:
            rec = {"scope": ev.scope, "key": key, "start_ns": start_ns, "parent": parent,
                   "turn": turn, "attrs": {}, "synthetic_key": synthetic}
            self._merge(rec, ev)
            self.state["open"][slot] = rec
        elif ev.phase == UPDATE:
            rec = self.state["open"].get(slot)
            if rec is not None:
                self._merge(rec, ev)
        else:  # END / INSTANT
            rec = self.state["open"].pop(slot, None) if ev.phase == END else None
            if rec is None:
                rec = {"scope": ev.scope, "key": key, "start_ns": start_ns, "parent": parent,
                       "turn": turn, "attrs": {}, "synthetic_key": synthetic}
            self._merge(rec, ev)
            sid = span_id(self.cfg.app, self.sid, ev.scope, key)
            self._emit(ev.scope, sid, rec["parent"], rec["start_ns"], self.now, rec, event, rec.get("turn"))

    def _apply_session(self, ev: SpanEvent, event: str, session: Dict[str, Any]) -> None:
        self._merge(session, ev)
        if ev.phase == START:
            self._emit_root(event)
        elif ev.phase in (END, INSTANT):
            for slot, rec in list(self.state["open"].items()):
                if rec["scope"] == TURN:
                    del self.state["open"][slot]
                    rec["incomplete"] = True
                    self._end_turn(rec["key"], rec, event)
            self._close_children(None, event)
            self._emit_root(event)
            self.state["_delete"] = True

    def _apply_turn(self, ev: SpanEvent, event: str, start_ns: int) -> None:
        key = ev.key
        if not key:
            return
        slot = f"{TURN}:{key}"
        if ev.phase == START:
            if key in self.state["ended_turns"]:
                self.state["ended_turns"].remove(key)
            rec = self._ensure_turn(key, start_ns)
            if rec is not None:
                self._merge(rec, ev)
                self.state["current_turn"] = key
        elif ev.phase == UPDATE:
            rec = self._ensure_turn(key, start_ns)
            if rec is not None:
                self._merge(rec, ev)
        else:
            rec = self.state["open"].pop(slot, None)
            if rec is None:
                rec = {"scope": TURN, "key": key, "start_ns": start_ns, "attrs": {}, "parent": self.root}
            self._merge(rec, ev)
            self._end_turn(key, rec, event)
            self._emit_root(event)


def otlp_attributes(attrs: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for key, value in attrs.items():
        encoded = _otlp_value(value)
        if encoded is not None:
            out.append({"key": key, "value": encoded})
    return out


def _otlp_value(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, (list, tuple)):
        values = [v for v in (_otlp_value(item) for item in value) if v is not None]
        return {"arrayValue": {"values": values}}
    return {"stringValue": str(value)}


# ---------------------------------------------------------------- pipeline


def load_adapter(app: str) -> Any:
    if not re.fullmatch(r"[a-z0-9_]+", app):
        raise ValueError("adapter name must match [a-z0-9_]+")
    return importlib.import_module(f"adapters.{app}")


def resolve_event(adapter: Any, argv_event: Optional[str], payload: Dict[str, Any]) -> str:
    resolver = getattr(adapter, "event_name", None)
    if resolver is not None:
        return resolver(argv_event, payload) or ""
    return argv_event or str(payload.get("hook_event_name") or "")


def respond(adapter: Any, event: str, payload: Dict[str, Any]) -> str:
    fn = getattr(adapter, "respond", None)
    if fn is None:
        return "{}"
    try:
        return fn(event, payload) or "{}"
    except Exception:
        return "{}"


def build_spans(adapter: Any, cfg: Config, event: str, payload: Dict[str, Any],
                now_ns: Optional[int] = None) -> List[Dict[str, Any]]:
    """Map one hook invocation to finished OTLP spans, updating state."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    events = [ev for ev in adapter.parse(event, payload) if ev.session_id]
    by_session: Dict[str, List[SpanEvent]] = {}
    for ev in events:
        by_session.setdefault(str(ev.session_id), []).append(ev)
    spans: List[Dict[str, Any]] = []
    for sid, evs in by_session.items():
        with session_state(cfg, sid) as state:
            builder = SpanBuilder(cfg, adapter, state, sid, now_ns)
            for ev in evs:
                builder.apply(ev, event)
            spans.extend(builder.spans)
        if any(ev.scope == SESSION for ev in evs):
            sweep_state(cfg)
    return spans


def build_body(adapter: Any, cfg: Config, event: str, payload: Dict[str, Any],
               spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    resource = {
        "service.name": getattr(adapter, "SERVICE_NAME", cfg.app),
        "project_name": cfg.project_name,
        "project_type": "observe",
        "telemetry.sdk.name": SCOPE_NAME,
        "telemetry.sdk.version": VERSION,
        "coding_agent.app": cfg.app,
        "coding_agent.content_captured": cfg.capture_content,
    }
    extra = getattr(adapter, "resource_attributes", None)
    if extra is not None:
        with contextlib.suppress(Exception):
            for key, value in (extra(event, payload) or {}).items():
                resource.setdefault(key, value)
    return {"resourceSpans": [{
        "resource": {"attributes": otlp_attributes(resource)},
        "scopeSpans": [{"scope": {"name": SCOPE_NAME, "version": VERSION}, "spans": spans}],
    }]}


def post(cfg: Config, body: Dict[str, Any]) -> int:
    """POST the OTLP/JSON body. Returns the HTTP status (raises on network error)."""
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(cfg.endpoint, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "X-Api-Key": cfg.api_key,
        "X-Secret-Key": cfg.secret_key,
        "User-Agent": f"{SCOPE_NAME}/{VERSION}",
    })
    # Environment proxies only: the macOS system-proxy lookup is not fork-safe.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(urllib.request.getproxies_environment()))
    try:
        with opener.open(request, timeout=cfg.timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def log(cfg: Config, message: str) -> None:
    if not cfg.log_file:
        return
    with contextlib.suppress(OSError):
        with open(cfg.log_file, "a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {cfg.app} {message}\n")


def deliver(cfg: Config, body: Dict[str, Any], label: str) -> None:
    """Send in a detached child (default) or inline (FI_HOOK_SYNC=1)."""
    if cfg.dump_file:
        with contextlib.suppress(OSError):
            with open(cfg.dump_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(body, separators=(",", ":")) + "\n")
    if not cfg.sync and hasattr(os, "fork"):
        try:
            pid = os.fork()
        except OSError:
            pid = -1
        if pid > 0:
            return
        if pid == 0:
            try:
                os.setsid()
                devnull = os.open(os.devnull, os.O_RDWR)
                for fd in (0, 1, 2):
                    os.dup2(devnull, fd)
                _send_logged(cfg, body, label)
            finally:
                os._exit(0)
    _send_logged(cfg, body, label)


def _send_logged(cfg: Config, body: Dict[str, Any], label: str) -> None:
    try:
        status = post(cfg, body)
        log(cfg, f"{label} http={status}")
    except Exception as exc:  # never surface payloads or headers
        log(cfg, f"{label} error={type(exc).__name__}")


def load_env_file(path: Optional[str], env: Dict[str, str]) -> None:
    """Fill FI_* keys missing from ``env`` from a KEY=VALUE file."""
    candidate = Path(path).expanduser() if path else DEFAULT_ENV_FILE.expanduser()
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if key.startswith("FI_") and key not in env:
            env[key] = value.strip().strip("'\"")


def parse_args(argv: List[str]) -> Tuple[str, Optional[str], Optional[str]]:
    app, event, env_file = "", None, None
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--env-file" and rest:
            env_file = rest.pop(0)
        elif arg.startswith("--env-file="):
            env_file = arg.split("=", 1)[1]
        elif not app:
            app = arg
        elif event is None:
            event = arg
    return app, event, env_file


def run(argv: List[str], stdin_text: str, env: Mapping[str, str]) -> str:
    """Process one hook call. Returns stdout text; never raises."""
    app, argv_event, env_file = parse_args(argv)
    env = dict(env)
    load_env_file(env_file or env.get("FI_HOOK_ENV_FILE"), env)
    try:
        adapter = load_adapter(app)
    except Exception:
        return "{}"
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    event = ""
    try:
        event = resolve_event(adapter, argv_event, payload)
    except Exception:
        pass
    out = respond(adapter, event, payload)
    try:
        cfg = Config.from_env(app, env)
        if not cfg.can_export:
            return out
        spans = build_spans(adapter, cfg, event, payload)
        if spans:
            body = build_body(adapter, cfg, event, payload, spans)
            _write_stdout(out)
            deliver(cfg, body, f"event={event} spans={len(spans)}")
            return ""
    except Exception as exc:
        with contextlib.suppress(Exception):
            log(Config.from_env(app, env), f"event={event} failed={type(exc).__name__}")
    return out


def _write_stdout(text: str) -> None:
    if text:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        stdin_text = sys.stdin.read()
    except Exception:
        stdin_text = ""
    try:
        out = run(sys.argv[1:], stdin_text, os.environ)
    except Exception:
        out = "{}"
    with contextlib.suppress(Exception):
        _write_stdout(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
