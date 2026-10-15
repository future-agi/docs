"""Contract tests for bridge.py against real Codex 0.162.1 OTLP/JSON log exports.

Fixtures are the request bodies `codex exec` (0.162.1) sent to an OTLP/HTTP
logs endpoint with `protocol = "json"`, one request per line:
  codex-0.162.1-default.jsonl       log_user_prompt = false (the default)
  codex-0.162.1-prompt-optin.jsonl  log_user_prompt = true
Only the host name and the local user name were replaced. Codex puts tool
arguments and tool output on codex.tool_result by default, so the default
fixture still carries content the bridge must drop.

Run: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import bridge  # noqa: E402

FIXTURES = HERE / "fixtures"
DEFAULT = FIXTURES / "codex-0.162.1-default.jsonl"
OPTIN = FIXTURES / "codex-0.162.1-prompt-optin.jsonl"


def bodies(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class Sink:
    def __init__(self):
        self.payloads = []
        self.headers = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                outer.payloads.append(json.loads(raw))
                outer.headers.append(dict(self.headers))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/tracer/v1/traces"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def spans(self):
        out = []
        for p in self.payloads:
            for rs in p["resourceSpans"]:
                res = bridge.kv(rs["resource"]["attributes"])
                for ss in rs["scopeSpans"]:
                    for s in ss["spans"]:
                        out.append((res, s, bridge.kv(s["attributes"])))
        return out


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.sink = Sink()
        self.addCleanup(self.sink.server.shutdown)

    def run_fixture(self, path: Path, **env):
        cfg = bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_PROJECT_NAME": "codex-contract",
                             "FI_OTLP_ENDPOINT": self.sink.url, **env})
        b = bridge.Bridge(cfg)
        for body in bodies(path):
            b.receive(body)
        b.flush(force=True)
        return self.sink.spans()

    def test_one_trace_per_turn_with_session_llm_and_tools(self):
        spans = self.run_fixture(DEFAULT)
        self.assertEqual(len({s["traceId"] for _, s, _ in spans}), 1)
        roots = [(s, a) for _, s, a in spans if "parentSpanId" not in s]
        self.assertEqual(len(roots), 1)
        root, ra = roots[0]
        self.assertEqual(root["name"], "Codex turn")
        self.assertEqual(ra["fi.span.kind"], "AGENT")
        self.assertTrue(ra["session.id"])
        self.assertEqual(ra["gen_ai.request.model"], "gpt-5.6-terra")
        self.assertEqual(ra["codex.approval_policy"], "never")

        llms = [(s, a) for _, s, a in spans if a["fi.span.kind"] == "LLM"]
        self.assertEqual(len(llms), 2)
        for s, a in llms:
            self.assertEqual(s["parentSpanId"], root["spanId"])
            self.assertGreater(a["gen_ai.usage.input_tokens"], 0)
            self.assertGreater(a["gen_ai.usage.output_tokens"], 0)
            self.assertEqual(a["http.response.status_code"], 200)
        self.assertEqual(ra["codex.turn.input_tokens"], sum(a["gen_ai.usage.input_tokens"] for _, a in llms))
        self.assertNotIn("gen_ai.usage.input_tokens", ra)  # would double the trace's token total

        tools = {s["name"]: (s, a) for _, s, a in spans if a["fi.span.kind"] == "TOOL"}
        self.assertEqual(set(tools), {"exec", "exec_command"})
        outer, inner = tools["exec"][0], tools["exec_command"][0]
        self.assertEqual(outer["parentSpanId"], root["spanId"])
        self.assertEqual(inner["parentSpanId"], outer["spanId"])  # code-mode nested call
        self.assertEqual(tools["exec_command"][1]["codex.decision"], "approved")
        for s, _ in tools.values():
            self.assertNotIn("status", s)

        for res, _, _ in spans:
            self.assertEqual(res["project_name"], "codex-contract")
            self.assertEqual(res["service.version"], "0.162.1")
        self.assertEqual(self.sink.headers[0]["X-Api-Key"], "k")

    def test_default_drops_prompt_and_tool_content(self):
        spans = self.run_fixture(DEFAULT)
        dump = json.dumps([s for _, s, _ in spans])
        self.assertNotIn("demo-project", dump)  # README text and ls output from tool_result
        self.assertNotIn("rg --files", dump)
        for _, s, a in spans:
            self.assertNotIn("input.value", a)
            self.assertNotIn("output.value", a)
        self.assertNotIn("dev-mac.local", json.dumps(self.sink.payloads))  # host.name is not forwarded

    def test_prompt_needs_both_codex_and_bridge_opt_in(self):
        spans = self.run_fixture(OPTIN)  # Codex sent the prompt, bridge content off
        self.assertNotIn("MARKER-CODEX-FIXTURE-OPTIN", json.dumps(self.sink.payloads))
        self.sink.payloads.clear()
        spans = self.run_fixture(OPTIN, FI_BRIDGE_CAPTURE_CONTENT="1")
        (root,) = [a for _, s, a in spans if "parentSpanId" not in s]
        self.assertIn("MARKER-CODEX-FIXTURE-OPTIN", root["input.value"])
        tool = [a for _, s, a in spans if s["name"] == "exec_command"][0]
        self.assertIn("README.md", tool["input.value"])
        self.assertIn("demo-project", tool["output.value"])

    def test_content_cap(self):
        spans = self.run_fixture(OPTIN, FI_BRIDGE_CAPTURE_CONTENT="1", FI_BRIDGE_MAX_CONTENT_CHARS="20")
        for _, _, a in spans:
            for k in ("input.value", "output.value"):
                if k in a:
                    self.assertLessEqual(len(a[k]), 20 + len("...[truncated]"))

    def test_errors_mark_spans(self):
        cid = "conv-err"

        def ev(name, **attrs):
            attrs.update({"event.name": name, "conversation.id": cid, "model": "gpt-5.6-terra",
                          "event.timestamp": "2026-10-14T20:00:0%d.000Z" % ev.n})
            ev.n += 1
            return {"key": None, "attributes": [{"key": k, "value": {"stringValue": str(v)}} for k, v in attrs.items()]}
        ev.n = 0
        records = [ev("codex.user_prompt", prompt="[REDACTED]", prompt_length="7"),
                   ev("codex.api_request", duration_ms="120", **{"http.response.status_code": "404",
                                                                  "error.message": "model_not_found"}),
                   ev("codex.tool_result", tool_name="exec_command", call_id="c1", duration_ms="5",
                      success="false", arguments="{\"cmd\":\"secret\"}", output="boom")]
        body = {"resourceLogs": [{"resource": {"attributes": []}, "scopeLogs": [{"logRecords": records}]}]}
        b = bridge.Bridge(bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url}))
        b.receive(body)
        b.flush(force=True)
        by_name = {s["name"]: s for _, s, _ in self.sink.spans()}
        self.assertEqual(by_name["Codex model request"]["status"], {"code": 2, "message": "model_not_found"})
        self.assertEqual(by_name["exec_command"]["status"]["code"], 2)
        self.assertEqual(by_name["Codex turn"]["status"]["code"], 2)
        self.assertNotIn("secret", json.dumps(self.sink.payloads))

    def test_late_events_join_the_same_trace(self):
        cfg = bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url})
        b = bridge.Bridge(cfg)
        batches = bodies(DEFAULT)
        b.receive(batches[0])
        b.flush(force=True)  # idle flush in the middle of the turn
        for body in batches[1:]:
            b.receive(body)
        b.flush(force=True)
        spans = self.sink.spans()
        self.assertEqual(len({s["traceId"] for _, s, _ in spans}), 1)
        roots = [s for _, s, _ in spans if "parentSpanId" not in s]
        self.assertEqual(len({r["spanId"] for r in roots}), 1)  # same turn span, sent again
        self.assertGreater(int(roots[-1]["endTimeUnixNano"]), int(roots[0]["endTimeUnixNano"]))

    def test_http_server_accepts_json_and_rejects_other_paths(self):
        cfg = bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url})
        b = bridge.Bridge(cfg)
        server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(b))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        for body in bodies(DEFAULT):
            req = urllib.request.Request(url + "/v1/logs", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200)
        b.flush(force=True)
        self.assertTrue(self.sink.spans())
        req = urllib.request.Request(url + "/v1/traces", data=b"{}", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
