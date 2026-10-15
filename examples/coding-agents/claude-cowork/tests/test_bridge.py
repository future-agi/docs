"""Contract tests for bridge.py.

fixtures/cowork-documented-session.jsonl holds OTLP/JSON log export requests
built from the Cowork monitoring reference (https://claude.com/docs/cowork/monitoring,
read 2026-10-14): the six documented events with their documented attributes,
the standard attributes (including user.email and workspace.host_paths) and the
documented resource attributes. Content is filled in, as a first-party
deployment with otlpContentCapture unset exports it. Event names are carried
in the documented `event.name` attribute; the record body and scope are
modelled on Claude Code 2.1.300's export of the same events, since Cowork's
reference documents attributes, not the envelope.

Run: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import bridge  # noqa: E402

FIXTURE = HERE / "fixtures" / "cowork-documented-session.jsonl"
P1 = "c0a8f3e2-41d7-4b9a-8e2c-7d1f5a6b3c90"
P2 = "d1b9e4f3-52e8-4cab-9f3d-8e2a6b7c4da1"
CONTENT_MARKERS = ("PROMPT_MARKER_COWORK", "RESPONSE_MARKER_COWORK", "TOOL_INPUT_MARKER_COWORK", "ERROR_MARKER_COWORK")
NEVER = ("fixture.user@example.com", "/Users/fixture", "Q3-board-pack", "fixture-login", "cfo@example.com",
         "user_01BWBeN28fixture", "mcp_server_name")


def bodies():
    return [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]


class Sink:
    def __init__(self):
        self.payloads = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                outer.payloads.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")))))
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


class CoworkBridgeTest(unittest.TestCase):
    def setUp(self):
        self.sink = Sink()
        self.addCleanup(self.sink.server.shutdown)

    def run_fixture(self, **env):
        b = bridge.Bridge(bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_PROJECT_NAME": "cowork-contract",
                                         "FI_OTLP_ENDPOINT": self.sink.url, **env}))
        for body in bodies():
            b.receive(body)
        b.flush(force=True)
        return self.sink.spans()

    def test_one_trace_per_prompt_id(self):
        spans = self.run_fixture()
        traces = {s["traceId"] for _, s, _ in spans}
        self.assertEqual(traces, {P1.replace("-", ""), P2.replace("-", "")})
        roots = {s["traceId"]: (s, a) for _, s, a in spans if "parentSpanId" not in s}
        self.assertEqual(len(roots), 2)
        for root, a in roots.values():
            self.assertEqual(root["name"], "Cowork prompt")
            self.assertEqual(a["fi.span.kind"], "AGENT")
            self.assertEqual(a["session.id"], "7f3c2a10-5b7e-4c1d-9a8e-2f6b1c0d4e51")
            self.assertEqual(a["user.id"], "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d")  # account uuid, not email
            self.assertEqual(a["gen_ai.request.model"], "claude-sonnet-5")
        for res, _, _ in spans:
            self.assertEqual(res, {"project_name": "cowork-contract", "service.name": "cowork",
                                   "service.version": "1.22209.3"})

    def test_first_prompt_tree(self):
        spans = [(s, a) for _, s, a in self.run_fixture() if s["traceId"] == P1.replace("-", "")]
        root = [s for s, _ in spans if "parentSpanId" not in s][0]
        llms = [(s, a) for s, a in spans if a["fi.span.kind"] == "LLM"]
        self.assertEqual(len(llms), 2)
        first = llms[0][1]
        self.assertEqual(first["gen_ai.usage.input_tokens"], 1200 + 9000 + 400)
        self.assertEqual(first["gen_ai.usage.output_tokens"], 180)
        self.assertEqual(first["gen_ai.usage.cache_read.input_tokens"], 9000)
        self.assertAlmostEqual(first["gen_ai.cost.total"], 0.0123)
        self.assertEqual(int(llms[0][0]["endTimeUnixNano"]) - int(llms[0][0]["startTimeUnixNano"]), 3100 * 10**6)
        tools = {s["name"]: (s, a) for s, a in spans if a["fi.span.kind"] == "TOOL"}
        self.assertEqual(set(tools), {"Read", "Bash"})
        self.assertEqual(tools["Read"][1]["cowork.decision"], "accept")
        self.assertEqual(tools["Bash"][1]["cowork.decision"], "reject")  # tool_decision without tool_result
        for s, _ in spans:
            if s is not root:
                self.assertEqual(s["parentSpanId"], root["spanId"])
        root_attrs = [a for s, a in spans if s is root][0]
        self.assertEqual(root_attrs["cowork.prompt.input_tokens"], 10600 + 10700)
        self.assertNotIn("gen_ai.usage.input_tokens", root_attrs)  # would double the trace's token total
        self.assertEqual(root_attrs["cowork.tool_calls"], 1)

    def test_errors(self):
        spans = [(s, a) for _, s, a in self.run_fixture() if s["traceId"] == P2.replace("-", "")]
        by = {}
        for s, a in spans:
            by.setdefault(s["name"], []).append((s, a))
        failed_llm = [s for s, a in by["Cowork model request"] if "status" in s][0]
        self.assertEqual(failed_llm["status"]["code"], 2)
        self.assertIn("rate_limit_error", failed_llm["status"]["message"])
        tool = by["mcp__gmail__create_draft"][0][0]
        self.assertEqual(tool["status"], {"code": 2, "message": "tool failed"})  # error text is content
        root = [s for s, _ in spans if "parentSpanId" not in s][0]
        self.assertEqual(root["status"]["code"], 2)

    def test_default_strips_content_and_identity(self):
        self.run_fixture()
        dump = json.dumps(self.sink.payloads)
        for marker in CONTENT_MARKERS + NEVER:
            self.assertNotIn(marker, dump)
        for _, _, a in self.sink.spans():
            self.assertNotIn("input.value", a)
            self.assertNotIn("output.value", a)

    def test_content_opt_in_never_sends_identity(self):
        spans = self.run_fixture(FI_BRIDGE_CAPTURE_CONTENT="1")
        dump = json.dumps(self.sink.payloads)
        for marker in CONTENT_MARKERS:
            self.assertIn(marker, dump)
        for marker in ("fixture.user@example.com", "/Users/fixture/Documents/Q3-board-pack\"", "fixture-login",
                       "user_01BWBeN28fixture", "mcp_server_name"):
            self.assertNotIn(marker, dump)  # tool_parameters and identity stay out
        root1 = [a for _, s, a in spans if s["traceId"] == P1.replace("-", "") and "parentSpanId" not in s][0]
        self.assertIn("PROMPT_MARKER_COWORK", root1["input.value"])
        self.assertIn("RESPONSE_MARKER_COWORK", root1["output.value"])

    def test_late_events_join_the_prompt(self):
        b = bridge.Bridge(bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url}))
        batches = bodies()
        b.receive(batches[0])
        b.flush(force=True)
        b.receive(batches[1])
        b.flush(force=True)
        spans = [(s, a) for _, s, a in self.sink.spans() if s["traceId"] == P1.replace("-", "")]
        roots = [s for s, _ in spans if "parentSpanId" not in s]
        self.assertEqual(len({r["spanId"] for r in roots}), 1)
        self.assertEqual(len([1 for s, a in spans if a["fi.span.kind"] == "LLM"]), 2)

    def test_http_token_and_paths(self):
        b = bridge.Bridge(bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url,
                                         "FI_BRIDGE_TOKEN": "t0ken"}))
        server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(b))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/v1/logs"
        data = json.dumps(bodies()[0]).encode()

        def post(headers):
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code

        self.assertEqual(post({}), 401)
        self.assertEqual(post({"Authorization": "Bearer wrong"}), 401)
        self.assertEqual(post({"Authorization": "Bearer t0ken"}), 200)
        url = url[: -len("/v1/logs")] + "/v1/traces"
        self.assertEqual(post({"Authorization": "Bearer t0ken"}), 404)
        url = url[: -len("/v1/traces")] + "/"  # endpoint entered without the /v1/logs path
        self.assertEqual(post({"Authorization": "Bearer t0ken"}), 200)
        b.flush(force=True)
        self.assertTrue(self.sink.spans())

    def test_prefixed_event_names(self):
        body = bodies()[0]
        for rl in body["resourceLogs"]:
            for sl in rl["scopeLogs"]:
                for rec in sl["logRecords"]:
                    for a in rec["attributes"]:
                        if a["key"] == "event.name":
                            a["value"]["stringValue"] = "cowork." + a["value"]["stringValue"]
        self.assertEqual([e["name"] for e in bridge.log_events(body)], ["user_prompt", "api_request"])


if __name__ == "__main__":
    unittest.main()
