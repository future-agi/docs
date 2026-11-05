"""STANDIN for the Managed Agents Sessions API (beta managed-agents-2026-04-01).

A local stub so the REAL anthropic Python SDK can run its documented session
flow with no Anthropic account and no spend. Only the remote endpoint is
swapped (base_url). It is not Anthropic's agent loop: there is no model, the
"agent" is a fixed script:

  user.message            -> session.status_running, agent.message,
                             agent.custom_tool_use(count_files), session.status_idle(requires_action)
  user.custom_tool_result -> session.status_running, agent.message, session.status_idle(end_turn)

Wire shapes follow the SDK 1.15.0 models (BetaManagedAgentsSession, the
BetaManagedAgents*Event types, SyncPageCursor) and the SSE framing the SDK
decodes (`event: <type>` + `data: <json>`). Unknown session ids return a 404
`not_found_error` body. Usage: python sessions_stub.py <port>
"""
from __future__ import annotations

import json
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def eid() -> str:
    return "sevt_" + secrets.token_hex(12)


class Session:
    def __init__(self, sid: str, agent_id: str, env_id: str):
        self.sid, self.agent_id, self.env_id = sid, agent_id, env_id
        self.created = now()
        self.events: list[dict] = []
        self.cond = threading.Condition()

    def obj(self, status: str = "idle") -> dict:
        return {
            "id": self.sid, "type": "session", "status": status, "title": None,
            "agent": {
                "id": self.agent_id, "type": "agent", "version": 1, "name": "repo-helper",
                "description": None, "system": None,
                "model": {"id": "claude-opus-5-5"},
                "execution_identity": {"type": "service_account"},
                "mcp_servers": [], "skills": [],
                "tools": [{"type": "custom", "name": "count_files", "description": "Count files matching a pattern",
                           "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}},
                                            "required": ["pattern"]}}],
            },
            "environment_id": self.env_id, "metadata": {}, "outcome_evaluations": [], "resources": [],
            "stats": {"active_seconds": 0.0, "duration_seconds": 0.0},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "active_seconds": 0.0},
            "vault_ids": [], "created_at": self.created, "updated_at": now(), "archived_at": None,
        }

    def append(self, ev: dict) -> dict:
        ev.setdefault("id", eid())
        ev.setdefault("processed_at", now())
        with self.cond:
            self.events.append(ev)
            self.cond.notify_all()
        return ev

    def agent_reacts(self, ev: dict) -> None:
        time.sleep(0.15)
        if ev["type"] == "user.message":
            text = " ".join(b.get("text", "") for b in ev.get("content", []) if b.get("type") == "text")
            pattern = text.split()[-1] if text.split() else "*"
            self.append({"type": "session.status_running"})
            self.append({"type": "agent.message", "content": [{"type": "text", "text": "I'll count the files."}]})
            tu = self.append({"type": "agent.custom_tool_use", "name": "count_files", "input": {"pattern": pattern}})
            self.append({"type": "session.status_idle", "stop_reason": {"type": "requires_action",
                                                                         "event_ids": [tu["id"]]}})
        elif ev["type"] == "user.custom_tool_result":
            result = " ".join(b.get("text", "") for b in (ev.get("content") or []) if b.get("type") == "text")
            self.append({"type": "session.status_running"})
            self.append({"type": "agent.message", "content": [{"type": "text", "text": f"Result: {result}"}]})
            self.append({"type": "session.status_idle", "stop_reason": {"type": "end_turn"}})


SESSIONS: dict[str, Session] = {}
ROUTE = re.compile(r"^/v1/sessions(?:/(?P<sid>[^/?]+))?(?P<rest>/events(?:/stream)?)?$")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep stdout quiet; never log headers
        sys.stderr.write("stub %s %s\n" % (self.command, self.path.split("?")[0]))

    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("request-id", "req_stub" + secrets.token_hex(8))
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _not_found(self, sid: str) -> None:
        self._json(404, {"type": "error", "error": {"type": "not_found_error",
                                                     "message": "session not found"}})

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        m = ROUTE.match(self.path.split("?")[0])
        if not m:
            return self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "no route"}})
        sid, rest = m.group("sid"), m.group("rest")
        if sid is None:
            body = self._body()
            agent = body.get("agent")
            agent_id = agent if isinstance(agent, str) else (agent or {}).get("id", "agent_stub")
            s = Session("sesn_" + secrets.token_hex(12), agent_id, body.get("environment_id", "env_stub"))
            SESSIONS[s.sid] = s
            return self._json(200, s.obj())
        s = SESSIONS.get(sid)
        if s is None:
            return self._not_found(sid)
        if rest == "/events":
            out = []
            for ev in self._body().get("events", []):
                ev = s.append(dict(ev))
                out.append(ev)
                threading.Thread(target=s.agent_reacts, args=(ev,), daemon=True).start()
            return self._json(200, {"data": out})
        return self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "no route"}})

    def do_GET(self):
        m = ROUTE.match(self.path.split("?")[0])
        if not m or m.group("sid") is None:
            return self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "no route"}})
        s = SESSIONS.get(m.group("sid"))
        if s is None:
            return self._not_found(m.group("sid"))
        rest = m.group("rest")
        if rest is None:
            return self._json(200, s.obj())
        if rest == "/events":
            return self._json(200, {"data": list(s.events), "next_page": None})
        # SSE stream: only events after the stream opens, as the real stream does.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        idx = len(s.events)
        try:
            while True:
                with s.cond:
                    while idx >= len(s.events):
                        if not s.cond.wait(timeout=15):
                            return
                    batch = s.events[idx:]
                    idx = len(s.events)
                for ev in batch:
                    self.wfile.write(f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode())
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            self.close_connection = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18267
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    print(f"sessions stub on 127.0.0.1:{port}", flush=True)
    srv.serve_forever()
