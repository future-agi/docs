"""Contract tests for collector.yaml against real Claude Code 2.1.300 exports.

The fixtures are OTLP/JSON trace exports captured from `claude -p` (v2.1.300)
with CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1: one run with the content flags
unset, one with OTEL_LOG_USER_PROMPTS, OTEL_LOG_TOOL_DETAILS and
OTEL_LOG_TOOL_CONTENT set to 1. Each test starts the real otelcol-contrib
binary with collector.yaml, posts a fixture to it, and checks what it forwards
to a loopback stand-in for Future AGI.

Run: OTELCOL_BIN=/path/to/otelcol-contrib python3 -m unittest discover -s tests
Skipped when no otelcol-contrib binary is found.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "collector.yaml"
FIXTURES = HERE / "fixtures"
DEFAULT_FIXTURE = FIXTURES / "claude-code-2.1.300-default.json"
CONTENT_FIXTURE = FIXTURES / "claude-code-2.1.300-content-optin.json"
OTELCOL = os.environ.get("OTELCOL_BIN") or shutil.which("otelcol-contrib")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def value(v: dict):
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return int(v[k]) if k == "intValue" else v[k]
    return v


def attrs(items) -> dict:
    return {a["key"]: value(a["value"]) for a in items or []}


class Sink:
    """Loopback stand-in for the Future AGI OTLP/HTTP endpoint (JSON encoding)."""

    def __init__(self):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                outer.requests.append((dict(self.headers), body))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/tracer/v1/traces"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@unittest.skipUnless(OTELCOL, "otelcol-contrib not found (set OTELCOL_BIN)")
class CollectorConfigTest(unittest.TestCase):
    def setUp(self):
        self.sink = Sink()
        self.port = free_port()
        self.tmp = tempfile.TemporaryDirectory()
        env = dict(os.environ, FI_API_KEY="test-api-key", FI_SECRET_KEY="test-secret-key",
                   FI_PROJECT_NAME="claude-code-contract", FI_OTLP_ENDPOINT=self.sink.url,
                   FI_COLLECTOR_LISTEN=f"127.0.0.1:{self.port}")
        # JSON encoding lets this test decode what the collector forwards
        # without protobuf libraries; everything else is collector.yaml as shipped.
        self.log = open(Path(self.tmp.name) / "otelcol.log", "w")
        self.proc = subprocess.Popen(
            [OTELCOL, "--config", str(CONFIG), "--set", "exporters::otlp_http/futureagi::encoding=json"],
            env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.2)
        self.fail("collector did not start: " + (Path(self.tmp.name) / "otelcol.log").read_text()[-2000:])

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)
        self.log.close()
        self.sink.close()
        self.tmp.cleanup()

    def send(self, body: dict) -> list:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/traces",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 200)
        deadline = time.time() + 15
        while time.time() < deadline and not self.sink.requests:
            time.sleep(0.2)
        self.assertTrue(self.sink.requests, "collector forwarded nothing")
        time.sleep(0.5)
        spans = []
        for headers, raw in self.sink.requests:
            self.headers = headers
            for rs in json.loads(raw)["resourceSpans"]:
                res = attrs(rs["resource"].get("attributes"))
                for ss in rs["scopeSpans"]:
                    for s in ss["spans"]:
                        spans.append((res, s, attrs(s.get("attributes"))))
        return spans

    def by_name(self, spans, name):
        return [(r, s, a) for r, s, a in spans if s["name"] == name]

    def test_span_kinds_tokens_and_project(self):
        spans = self.send(json.loads(DEFAULT_FIXTURE.read_text()))
        self.assertEqual(len(spans), 9)
        kinds = {s["name"]: a.get("fi.span.kind") for _, s, a in spans}
        self.assertEqual(kinds, {
            "claude_code.interaction": "AGENT",
            "claude_code.llm_request": "LLM",
            "Bash": "TOOL",  # tool spans are renamed after tool_name
            "Read": "TOOL",
            "claude_code.tool.blocked_on_user": "CHAIN",
            "claude_code.tool.execution": "CHAIN",
        })
        for _, s, a in spans:
            if a.get("fi.span.kind") == "TOOL":
                self.assertEqual(s["name"], a["tool_name"])
                self.assertEqual(a["span.type"], "tool")
        for _, _, a in self.by_name(spans, "claude_code.llm_request"):
            self.assertEqual(a["gen_ai.usage.input_tokens"],
                             a["input_tokens"] + a["cache_read_tokens"] + a["cache_creation_tokens"])
            self.assertEqual(a["gen_ai.usage.output_tokens"], a["output_tokens"])
            self.assertEqual(a["gen_ai.usage.cache_read.input_tokens"], a["cache_read_tokens"])
            self.assertEqual(a["gen_ai.request.model"], "claude-haiku-5-5")
        for res, _, a in spans:
            self.assertEqual(res["project_name"], "claude-code-contract")
            self.assertTrue(a["session.id"])
        # One trace, parented the way Claude Code sent it.
        self.assertEqual(len({s["traceId"] for _, s, _ in spans}), 1)
        self.assertEqual(self.headers.get("X-Api-Key"), "test-api-key")
        self.assertEqual(self.headers.get("X-Secret-Key"), "test-secret-key")
        self.assertNotIn("gzip", self.headers.get("Content-Encoding", ""))

    def test_default_export_carries_no_content(self):
        spans = self.send(json.loads(DEFAULT_FIXTURE.read_text()))
        for _, s, a in spans:
            self.assertNotIn("input.value", a, s["name"])
            self.assertNotIn("output.value", a, s["name"])
            self.assertNotIn("full_command", a)
            self.assertNotIn("file_path", a)
        (_, _, interaction), = self.by_name(spans, "claude_code.interaction")
        self.assertEqual(interaction["user_prompt"], "<REDACTED>")
        self.assertNotIn("MARKER-FIXTURE", json.dumps([s for _, s, _ in spans]))

    def test_content_opt_in_maps_prompt_and_tool_io(self):
        spans = self.send(json.loads(CONTENT_FIXTURE.read_text()))
        (_, _, interaction), = self.by_name(spans, "claude_code.interaction")
        self.assertIn("MARKER-FIXTURE-OPTIN", interaction["input.value"])
        tools = {s["name"]: a for _, s, a in spans if a.get("fi.span.kind") == "TOOL"}
        self.assertEqual(tools["Bash"]["input.value"], tools["Bash"]["full_command"])
        self.assertTrue(tools["Bash"]["output.value"])
        self.assertTrue(tools["Read"]["input.value"].endswith("README.md"))
        self.assertIn("# demo-project", tools["Read"]["output.value"])

    def test_user_email_is_dropped(self):
        body = json.loads(DEFAULT_FIXTURE.read_text())
        email = {"key": "user.email", "value": {"stringValue": "dev@example.com"}}
        for rs in body["resourceSpans"]:
            rs["resource"]["attributes"].append(copy.deepcopy(email))
            for ss in rs["scopeSpans"]:
                for s in ss["spans"]:
                    s["attributes"].append(copy.deepcopy(email))
        spans = self.send(body)
        self.assertNotIn("dev@example.com", json.dumps([[r, a] for r, _, a in spans]))

    def test_project_name_from_claude_code_wins(self):
        body = json.loads(DEFAULT_FIXTURE.read_text())
        for rs in body["resourceSpans"]:
            rs["resource"]["attributes"].append({"key": "project_name", "value": {"stringValue": "per-dev"}})
        spans = self.send(body)
        self.assertEqual({r["project_name"] for r, _, _ in spans}, {"per-dev"})


if __name__ == "__main__":
    unittest.main()
