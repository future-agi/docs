"""Shared helpers for emitter and adapter tests (stdlib only)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
EMIT = ROOT / "emit.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import emit  # noqa: E402


class Receiver:
    """Loopback OTLP/HTTP receiver that records (path, headers, body)."""

    def __init__(self, status: int = 200):
        self.requests: List[Tuple[str, Dict[str, str], Dict[str, Any]]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size) or b"{}")
                outer.requests.append((self.path, dict(self.headers), body))
                self.send_response(status)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):  # silence
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def wait_for(self, count: int, timeout: float = 10.0) -> None:
        deadline = time.time() + timeout
        while len(self.requests) < count and time.time() < deadline:
            time.sleep(0.02)

    def spans(self) -> List[Dict[str, Any]]:
        return [s for _, _, body in self.requests for s in all_spans(body)]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def all_spans(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for rs in body.get("resourceSpans", []) for ss in rs.get("scopeSpans", []) for s in ss.get("spans", [])]


def attrs(span_or_resource: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in span_or_resource.get("attributes", []):
        value = item["value"]
        out[item["key"]] = next(iter(value.values()))
    return out


def base_env(state_dir: str, endpoint: str = "http://127.0.0.1:9/v1/traces", **extra: str) -> Dict[str, str]:
    env = {
        "FI_API_KEY": "test-api-key",
        "FI_SECRET_KEY": "test-secret-key",
        "FI_PROJECT_NAME": "hook-test",
        "FI_OTLP_ENDPOINT": endpoint,
        "FI_HOOK_STATE_DIR": state_dir,
        "FI_HOOK_SYNC": "1",
        "FI_HOOK_TIMEOUT": "2",
    }
    env.update(extra)
    return env


def config(app: str, state_dir: str, **extra: str) -> "emit.Config":
    return emit.Config.from_env(app, base_env(state_dir, **extra))


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def replay(adapter: Any, cfg: "emit.Config", records: Iterable[Dict[str, Any]],
           start_ns: int = 1_800_000_000_000_000_000, step_ms: int = 1000) -> List[Dict[str, Any]]:
    """Run records through build_spans in-process with a fake clock."""
    spans: List[Dict[str, Any]] = []
    now = start_ns
    for record in records:
        now += step_ms * 1_000_000
        event = emit.resolve_event(adapter, record.get("argv_event"), record["payload"]) or record["event"]
        spans.extend(emit.build_spans(adapter, cfg, event, record["payload"], now_ns=now))
    return spans


def run_cli(args: List[str], payload: Any, env: Dict[str, str], timeout: float = 20) -> subprocess.CompletedProcess:
    full_env = {"PATH": os.environ.get("PATH", ""), "HOME": tempfile.gettempdir()}
    full_env.update(env)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(EMIT)] + args, input=text, capture_output=True,
                          text=True, env=full_env, timeout=timeout)


def by_name(spans: List[Dict[str, Any]], name: str) -> List[Dict[str, Any]]:
    return [s for s in spans if s["name"] == name]


def latest(spans: List[Dict[str, Any]], span_id: str) -> Optional[Dict[str, Any]]:
    """Last export of a span id (the root is re-exported as the session grows)."""
    found = [s for s in spans if s["spanId"] == span_id]
    return found[-1] if found else None
