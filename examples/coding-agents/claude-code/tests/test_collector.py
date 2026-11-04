"""Contract tests for collector.yaml against real Claude Code 2.1.300 exports.

The fixtures are OTLP/JSON trace exports captured from `claude -p` (v2.1.300)
with CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1: one run with the content flags
unset, one with OTEL_LOG_USER_PROMPTS, OTEL_LOG_TOOL_DETAILS and
OTEL_LOG_TOOL_CONTENT set to 1. Each test starts the real otelcol-contrib
binary with collector.yaml, posts a fixture to it, and checks what it forwards
to a loopback stand-in for Future AGI.

Two more default-flags runs: one called a tool on a stub stdio MCP server
named "zzsecretcorp" (tool "zz_internal_lookup"), one ran a Bash command and a
Read that both failed. In every fixture user.id is replaced with zeros.

Run: OTELCOL_BIN=/path/to/otelcol-contrib python3 -m unittest discover -s tests
Skipped when no otelcol-contrib binary is found, unless REQUIRE_OTELCOL=1.
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
MCP_FIXTURE = FIXTURES / "claude-code-2.1.300-mcp.json"
TOOL_ERROR_FIXTURE = FIXTURES / "claude-code-2.1.300-tool-error.json"
# Error text with a local path and user name, as a provider or gateway could
# return it for a failed model request.
SECRET_ERROR = "API Error: 500 cannot open /Users/probeuser/secret-project/.env (ERRMARK-77)"
OTELCOL = os.environ.get("OTELCOL_BIN") or shutil.which("otelcol-contrib")
if not OTELCOL and os.environ.get("REQUIRE_OTELCOL") == "1":
    raise RuntimeError("REQUIRE_OTELCOL=1 but no otelcol-contrib binary (set OTELCOL_BIN)")


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


def with_error_text(body: dict, error_class: str | None = "api_error") -> dict:
    """Mark the model-request and tool-execution spans failed with SECRET_ERROR."""
    for rs in body["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for s in ss["spans"]:
                if s["name"] not in ("claude_code.llm_request", "claude_code.tool.execution"):
                    continue
                s["status"] = {"code": 2, "message": SECRET_ERROR}
                s["attributes"] = [a for a in s["attributes"] if a["key"] != "success"]
                s["attributes"] += [{"key": "success", "value": {"boolValue": False}},
                                    {"key": "error", "value": {"stringValue": SECRET_ERROR}}]
                if error_class:
                    s["attributes"].append({"key": "error_class", "value": {"stringValue": error_class}})
    return body


@unittest.skipUnless(OTELCOL, "otelcol-contrib not found (set OTELCOL_BIN)")
class CollectorCase(unittest.TestCase):
    """Starts collector.yaml in otelcol-contrib for each test; no tests itself."""
    extra_env: dict = {}

    def setUp(self):
        self.sink = Sink()
        self.port = free_port()
        self.tmp = tempfile.TemporaryDirectory()
        env = dict(os.environ, FI_API_KEY="test-api-key", FI_SECRET_KEY="test-secret-key",
                   FI_PROJECT_NAME="claude-code-contract", FI_OTLP_ENDPOINT=self.sink.url,
                   FI_COLLECTOR_LISTEN=f"127.0.0.1:{self.port}", **self.extra_env)
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


class CollectorConfigTest(CollectorCase):
    """collector.yaml with its defaults."""

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
            self.assertEqual(a["gen_ai.usage.cache_read_tokens"], a["cache_read_tokens"])
            self.assertEqual(a["gen_ai.usage.cache_write_tokens"], a["cache_creation_tokens"])
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

    def test_independently_optional_cache_counts(self):
        # One request covers read-only, write-only, both and neither. Also
        # seed a stale derived total: recomputing must not double-count it.
        body = json.loads(DEFAULT_FIXTURE.read_text())
        expected = {}
        for rs in body["resourceSpans"]:
            for ss in rs["scopeSpans"]:
                model = next(s for s in ss["spans"] if s["name"] == "claude_code.llm_request")
                ss["spans"] = []
                for index, cache in enumerate((
                    {"cache_read_tokens": 90}, {"cache_creation_tokens": 40},
                    {"cache_read_tokens": 90, "cache_creation_tokens": 40}, {},
                    {"cache_read_tokens": 90},  # with a stale derived total
                ), start=1):
                    span = copy.deepcopy(model)
                    span["spanId"] = f"{index:016x}"
                    span["attributes"] = [a for a in span["attributes"] if a["key"] not in (
                        "input_tokens", "cache_read_tokens", "cache_creation_tokens",
                        "gen_ai.usage.input_tokens",
                    )]
                    usage = {"input_tokens": 10, **cache}
                    if index == 5:
                        usage["gen_ai.usage.input_tokens"] = 999
                    span["attributes"] += [
                        {"key": key, "value": {"intValue": str(count)}}
                        for key, count in usage.items()
                    ]
                    ss["spans"].append(span)
                    expected[span["spanId"]] = (10 + sum(cache.values()), cache)
        spans = self.by_name(self.send(body), "claude_code.llm_request")
        self.assertEqual(len(spans), 5)
        for _, span, attributes in spans:
            total, cache = expected[span["spanId"]]
            self.assertEqual(attributes["gen_ai.usage.input_tokens"], total)
            for source, mapped in (("cache_read_tokens", "gen_ai.usage.cache_read_tokens"),
                                   ("cache_creation_tokens", "gen_ai.usage.cache_write_tokens")):
                if source in cache:
                    self.assertEqual(attributes[mapped], cache[source])
                else:
                    self.assertNotIn(mapped, attributes)

    def test_mcp_names_replaced_by_default(self):
        spans = self.send(json.loads(MCP_FIXTURE.read_text()))
        dump = json.dumps([[r, s] for r, s, _ in spans])
        self.assertNotIn("zzsecretcorp", dump)
        self.assertNotIn("zz_internal_lookup", dump)
        names = {s["name"] for _, s, a in spans if a.get("fi.span.kind") == "TOOL"}
        self.assertEqual(names, {"mcp_other", "Read"})
        (mcp,) = [a for _, s, a in spans if s["name"] == "mcp_other"]
        self.assertEqual(mcp["gen_ai.tool.name"], "mcp_other")
        self.assertNotIn("anthropic.mcp.server.name", mcp)

    def test_project_name_from_claude_code_wins(self):
        body = json.loads(DEFAULT_FIXTURE.read_text())
        for rs in body["resourceSpans"]:
            rs["resource"]["attributes"].append({"key": "project_name", "value": {"stringValue": "per-dev"}})
        spans = self.send(body)
        self.assertEqual({r["project_name"] for r, _, _ in spans}, {"per-dev"})

    def test_error_text_dropped_by_default(self):
        spans = self.send(with_error_text(json.loads(DEFAULT_FIXTURE.read_text())))
        dump = json.dumps([[r, s] for r, s, _ in spans])
        for needle in ("probeuser", "/Users/", "ERRMARK", "secret-project"):
            self.assertNotIn(needle, dump)
        failed = [(s, a) for _, s, a in spans
                  if s["name"] in ("claude_code.llm_request", "claude_code.tool.execution")]
        self.assertEqual(len(failed), 4)
        for s, a in failed:
            self.assertEqual(s["status"]["code"], 2, s["name"])
            self.assertEqual(s["status"]["message"], "api_error")
            self.assertEqual(a["error_class"], "api_error")
            self.assertNotIn("error", a)

    def test_error_text_without_class_gets_fixed_message(self):
        spans = self.send(with_error_text(json.loads(DEFAULT_FIXTURE.read_text()), error_class=None))
        self.assertNotIn("probeuser", json.dumps([[r, s] for r, s, _ in spans]))
        for _, s, _ in self.by_name(spans, "claude_code.llm_request"):
            self.assertEqual(s["status"], {"code": 2, "message": "error"})

    def test_real_tool_errors_keep_status_and_class(self):
        # Claude Code 2.1.300 reports failed tools by error class only.
        spans = self.send(json.loads(TOOL_ERROR_FIXTURE.read_text()))
        self.assertNotIn("ERRMARK", json.dumps([[r, s] for r, s, _ in spans]))
        failed = {a["error_class"]: s["status"] for _, s, a in self.by_name(spans, "claude_code.tool.execution")}
        self.assertEqual(failed, {"ShellError": {"code": 2, "message": "ShellError"},
                                  "TelemetrySafeError": {"code": 2, "message": "TelemetrySafeError"}})
        self.assertEqual({s["name"] for _, s, a in spans if a.get("fi.span.kind") == "TOOL"}, {"Bash", "Read"})


class OptInTest(CollectorCase):
    """FI_KEEP_MCP_NAMES=1 and FI_KEEP_ERROR_TEXT=1 keep what the defaults remove."""
    extra_env = {"FI_KEEP_MCP_NAMES": "1", "FI_KEEP_ERROR_TEXT": "1"}

    def test_mcp_names_kept(self):
        spans = self.send(json.loads(MCP_FIXTURE.read_text()))
        (mcp,) = [a for _, s, a in spans if s["name"] == "mcp__zzsecretcorp__zz_internal_lookup"]
        self.assertEqual(mcp["gen_ai.tool.name"], "zz_internal_lookup")
        self.assertEqual(mcp["anthropic.mcp.server.name"], "zzsecretcorp")

    def test_error_text_kept(self):
        spans = self.send(with_error_text(json.loads(DEFAULT_FIXTURE.read_text())))
        for _, s, a in self.by_name(spans, "claude_code.llm_request"):
            self.assertEqual(s["status"]["message"], SECRET_ERROR)
            self.assertEqual(a["error"], SECRET_ERROR)


if __name__ == "__main__":
    unittest.main()
