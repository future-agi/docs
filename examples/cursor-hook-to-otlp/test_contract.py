#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
EMIT = ROOT / "emit.py"
seen: list[tuple[str, dict[str, str], dict]] = []


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size))
        seen.append((self.path, dict(self.headers), body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format, *args):
        return


def run(event: str, payload: dict, capture: bool = False) -> None:
    env = os.environ.copy()
    env.update({
        "FI_OTLP_ENDPOINT": f"http://127.0.0.1:{port}/tracer/v1/traces",
        "FI_API_KEY": "test-api-key",
        "FI_SECRET_KEY": "test-secret-key",
        "FI_PROJECT_NAME": "cursor-hook-contract",
        "CURSOR_CAPTURE_CONTENT": "true" if capture else "false",
    })
    result = subprocess.run(
        [sys.executable, str(EMIT), event],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr


server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    fixture = {
        "conversation_id": "conv-contract-001",
        "generation_id": "gen-001",
        "model": "fixture-model",
        "status": "ok",
        "tool_name": "Shell",
        "tool_input": {"command": "echo SECRET_FIXTURE_MARKER"},
        "prompt": "private prompt SECRET_FIXTURE_MARKER",
    }
    run("preToolUse", fixture)
    run("postToolUseFailure", {**fixture, "status": "error"})
    run("stop", fixture)
    assert len(seen) == 3
    for path, headers, body in seen:
        assert path == "/tracer/v1/traces"
        assert headers["X-Api-Key"] == "test-api-key"
        assert headers["X-Secret-Key"] == "test-secret-key"
        resource = body["resourceSpans"][0]["resource"]["attributes"]
        keys = {item["key"]: item["value"] for item in resource}
        assert keys["project_name"]["stringValue"] == "cursor-hook-contract"
        encoded = json.dumps(body)
        assert "SECRET_FIXTURE_MARKER" not in encoded
        assert "private prompt" not in encoded

    run("stop", fixture, capture=True)
    encoded = json.dumps(seen[-1][2])
    assert "SECRET_FIXTURE_MARKER" in encoded
    print("cursor hook contract: 3 privacy-off spans + 1 opt-in content span passed")
finally:
    server.shutdown()
