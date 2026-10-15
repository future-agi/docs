"""Contract tests for bridge.py.

fixtures/cowork-documented-session.jsonl holds OTLP/JSON log export requests
built from the Cowork monitoring reference (https://claude.com/docs/cowork/monitoring,
read 2026-10-14): the six documented events with their documented attributes,
the standard attributes (including user.email and workspace.host_paths) and the
documented resource attributes. Content is filled in, as a first-party
deployment with otlpContentCapture unset exports it. Event names are carried
in the documented `event.name` attribute; the record body and scope are
modelled on Claude Code 2.1.300's export of the same events, since Cowork's
reference documents attributes, not the envelope. The MCP call carries
tool_name "mcp_tool" with the server and tool names only in tool_parameters,
as Claude Code's monitoring reference documents for user-configured MCP
servers (https://code.claude.com/docs/en/monitoring-usage).

Run: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import gzip
import json
import os
import socket
import subprocess
import sys
import threading
import time
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
         "user_01BWBeN28fixture", "Number of requests", "tool_parameters")


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
        self.addCleanup(self.sink.server.server_close)
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
        self.assertEqual(failed_llm["status"]["message"], "HTTP 429 rate_limit_error")  # no free text by default
        tool, tool_attrs = by["mcp__gmail__create_draft"][0]  # tool_name is "mcp_tool"; names from tool_parameters
        self.assertEqual(tool["status"], {"code": 2, "message": "tool failed"})  # error text is content
        self.assertEqual((tool_attrs["cowork.tool_name"], tool_attrs["cowork.mcp_server_name"],
                          tool_attrs["cowork.mcp_tool_name"]), ("mcp_tool", "gmail", "create_draft"))
        root = [s for s, _ in spans if "parentSpanId" not in s][0]
        self.assertNotIn("status", root)  # the 429 was retried and the next request succeeded

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
        self.assertIn("Number of requests", dump)  # the API's error message is content
        for marker in ("fixture.user@example.com", "/Users/fixture/Documents/Q3-board-pack\"", "fixture-login",
                       "user_01BWBeN28fixture", "tool_parameters"):
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
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/v1/logs"
        data = json.dumps(bodies()[0]).encode()

        def post(headers):
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                e.close()
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

    # ------------------------------------------------------------ synthetic event sequences

    def mapped(self, *records, service="cowork", **env):
        b = bridge.Bridge(bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url,
                                         **env}))
        b.receive(batch(*records, service=service))
        b.flush(force=True)
        return self.sink.spans()

    def test_reject_then_accept_same_tool_keeps_the_reject(self):
        spans = self.mapped(rec("user_prompt", 0, 0),
                            rec("tool_decision", 1, 1, tool_name="Bash", decision="reject", source="config"),
                            rec("tool_decision", 2, 2, tool_name="Bash", decision="accept", source="user_temporary"),
                            rec("tool_result", 3, 3, tool_name="Bash", success="true", decision_type="accept",
                                decision_source="user_temporary", duration_ms="100"))
        tools = sorted((s["name"], a["cowork.decision"]) for _, s, a in spans if a["fi.span.kind"] == "TOOL")
        self.assertEqual(tools, [("Bash", "accept"), ("Bash", "reject")])
        root = [a for _, s, a in spans if "parentSpanId" not in s][0]
        self.assertEqual(root["cowork.tool_calls"], 1)  # the rejected call never ran

    def test_tool_use_id_pairs_decision_and_result(self):
        spans = self.mapped(rec("user_prompt", 0, 0),
                            rec("tool_decision", 1, 1, tool_name="Read", decision="accept", tool_use_id="toolu_1"),
                            rec("tool_decision", 2, 2, tool_name="Read", decision="reject", tool_use_id="toolu_2"),
                            rec("tool_result", 3, 3, tool_name="Read", success="true", tool_use_id="toolu_1"))
        tools = sorted((s["name"], a.get("cowork.decision", "")) for _, s, a in spans if a["fi.span.kind"] == "TOOL")
        self.assertEqual(tools, [("Read", ""), ("Read", "reject")])

    def test_prompt_error_only_when_the_last_model_request_failed(self):
        ok = self.mapped(rec("user_prompt", 0, 0, prompt=P1),
                         rec("api_error", 1, 1, prompt=P1, status_code="529", error="overloaded_error", attempt="1"),
                         rec("api_request", 2, 4, prompt=P1, input_tokens="10", output_tokens="5", attempt="2"))
        root = [s for _, s, _ in ok if "parentSpanId" not in s][0]
        self.assertNotIn("status", root)
        failed = [s for _, s, a in ok if a["fi.span.kind"] == "LLM" and "status" in s]
        self.assertEqual([s["status"]["message"] for s in failed], ["HTTP 529 overloaded_error"])
        self.sink.payloads.clear()
        spans = self.mapped(rec("user_prompt", 0, 0, prompt=P2),
                            rec("api_request", 1, 2, prompt=P2, input_tokens="10", output_tokens="5"),
                            rec("api_error", 2, 4, prompt=P2, status_code="500", error="api_error"))
        root = [s for _, s, _ in spans if "parentSpanId" not in s][0]
        self.assertEqual(root["status"], {"code": 2, "message": "model request failed"})

    def test_redelivered_batch_is_counted_once(self):
        b = bridge.Bridge(bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url}))
        body = batch(rec("user_prompt", 0, 0),
                     rec("api_request", 1, 1, input_tokens="100", output_tokens="7"),
                     rec("tool_result", 2, 2, tool_name="Read", success="true"))
        b.receive(body)
        b.receive(json.loads(json.dumps(body)))  # the exporter retried the same batch
        b.flush(force=True)
        spans = self.sink.spans()
        self.assertEqual(len(spans), 3)
        root = [a for _, s, a in spans if "parentSpanId" not in s][0]
        self.assertEqual((root["cowork.prompt.input_tokens"], root["cowork.prompt.output_tokens"],
                          root["cowork.tool_calls"]), (100, 7, 1))

    def test_session_and_user_on_every_span(self):
        spans = self.run_fixture()
        for _, s, a in spans:
            self.assertEqual(a["session.id"], "7f3c2a10-5b7e-4c1d-9a8e-2f6b1c0d4e51", s["name"])
            self.assertEqual(a["gen_ai.conversation.id"], "7f3c2a10-5b7e-4c1d-9a8e-2f6b1c0d4e51", s["name"])
            self.assertEqual(a["user.id"], "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d", s["name"])

    def test_tool_parameters_names_only(self):
        params = {
            "Skill": json.dumps({"skill_name": "xlsx"}),
            "Agent": json.dumps({"subagent_type": "general-purpose"}),
            "Bash": json.dumps({"bash_command": "cat /Users/alice/secret.txt", "full_command": "cat SECRET_CMD"}),
            "Read": json.dumps({"file_path": "/Users/alice/notes.md", "skill_name": "/Users/alice/.claude/skills/x"}),
        }
        records = [rec("user_prompt", 0, 0)]
        for i, (tool, p) in enumerate(params.items(), start=1):
            records.append(rec("tool_result", i, i, tool_name=tool, success="true", tool_parameters=p))
        records.append(rec("tool_decision", 9, 9, tool_name="mcp_tool", decision="reject", source="user_reject",
                           tool_parameters=json.dumps({"mcp_server_name": "jira", "mcp_tool_name": "create_issue"})))
        for env in ({}, {"FI_BRIDGE_CAPTURE_CONTENT": "1"}):
            self.sink.payloads.clear()
            spans = self.mapped(*records, **env)
            dump = json.dumps(self.sink.payloads)
            for marker in ("/Users/alice", "SECRET_CMD", "bash_command", "file_path"):
                self.assertNotIn(marker, dump)
            tools = {s["name"]: a for _, s, a in spans if a["fi.span.kind"] == "TOOL"}
            self.assertEqual(tools["Skill"]["cowork.skill_name"], "xlsx")
            self.assertEqual(tools["Agent"]["cowork.subagent_type"], "general-purpose")
            self.assertNotIn("cowork.skill_name", tools["Read"])  # a path is not a name
            self.assertEqual(tools["mcp__jira__create_issue"]["cowork.decision"], "reject")
            self.assertEqual(tools["mcp__jira__create_issue"]["gen_ai.tool.name"], "mcp__jira__create_issue")

    def test_api_error_text_needs_content_opt_in(self):
        err = "rate_limit_error: proxy https://gw.internal/v1 for /Users/alice/project rejected the request"
        records = (rec("user_prompt", 0, 0), rec("api_error", 1, 1, status_code="429", error=err))
        spans = self.mapped(*records)
        dump = json.dumps(self.sink.payloads)
        for marker in ("/Users/alice", "alice", "gw.internal"):
            self.assertNotIn(marker, dump)
        llm = [(s, a) for _, s, a in spans if a["fi.span.kind"] == "LLM"][0]
        self.assertEqual(llm[0]["status"]["message"], "HTTP 429 rate_limit_error")
        self.assertEqual(llm[1]["error.type"], "rate_limit_error")
        self.sink.payloads.clear()
        self.mapped(*records, FI_BRIDGE_CAPTURE_CONTENT="1")
        self.assertIn("/Users/alice/project", json.dumps(self.sink.payloads))

    def test_other_services_are_ignored(self):
        records = (rec("user_prompt", 0, 0), rec("api_request", 1, 1, input_tokens="1", output_tokens="1"))
        self.assertEqual(self.mapped(*records, service="claude-code"), [])
        spans = self.mapped(*records, service="claude-code", FI_BRIDGE_ACCEPT_ANY_SERVICE="1")
        self.assertEqual({res["service.name"] for res, _, _ in spans}, {"claude-code"})

    def test_non_numeric_sequence(self):
        spans = self.mapped(rec("user_prompt", "abc", 0), rec("api_request", "", 1, input_tokens="1"))
        self.assertEqual(len(spans), 2)

    # ------------------------------------------------------------ HTTP front

    def serve(self, **env):
        b = bridge.Bridge(bridge.Config({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_OTLP_ENDPOINT": self.sink.url,
                                         "FI_BRIDGE_TOKEN": "t0ken", **env}))
        server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(b))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return b, server.server_address[1]

    def raw_post(self, port, headers, body=b"", timeout=5):
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            head = "POST /v1/logs HTTP/1.1\r\nHost: x\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            s.sendall(head.encode() + b"\r\n" + body)
            data = b""
            while True:
                try:
                    chunk = s.recv(65536)
                except ConnectionResetError:  # the server closed with our unread body pending
                    break
                if not chunk:
                    break
                data += chunk
        return int(data.split(b" ", 2)[1])

    def test_http_bodies(self):
        b, port = self.serve()
        auth = {"Authorization": "Bearer t0ken", "Content-Type": "application/json"}
        data = json.dumps(bodies()[0]).encode()
        chunked = b"".join(b"%x\r\n%s\r\n" % (len(data[i:i + 700]), data[i:i + 700]) for i in range(0, len(data), 700))
        self.assertEqual(self.raw_post(port, {**auth, "Transfer-Encoding": "chunked"}, chunked + b"0\r\n\r\n"), 200)
        gz = gzip.compress(data)
        self.assertEqual(self.raw_post(port, {**auth, "Content-Encoding": "gzip", "Content-Length": len(gz)}, gz), 200)
        self.assertEqual(len(b.mapper.prompts), 1)
        self.assertEqual(self.raw_post(port, auth), 411)  # no length, not chunked: never a silent 200
        self.assertEqual(self.raw_post(port, {**auth, "Content-Length": bridge.MAX_BODY + 1}), 413)
        self.assertEqual(self.raw_post(port, {**auth, "Content-Encoding": "gzip", "Content-Length": 4}, b"nope"), 400)
        self.assertEqual(self.raw_post(port, {**auth, "Content-Encoding": "br", "Content-Length": 2}, b"{}"), 415)

    def test_token_is_checked_before_the_body_is_read(self):
        _, port = self.serve()
        start = time.monotonic()
        code = self.raw_post(port, {"Content-Type": "application/json", "Content-Length": 10**9})  # no body sent
        self.assertEqual(code, 401)
        self.assertLess(time.monotonic() - start, 3)

    def test_bridge_will_not_start_without_a_token(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("FI_")}
        env.update({"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_BRIDGE_LISTEN": "127.0.0.1:0"})
        r = subprocess.run([sys.executable, str(HERE.parent / "bridge.py")], env=env, capture_output=True,
                           text=True, timeout=10)
        self.assertEqual(r.returncode, 2)
        self.assertIn("FI_BRIDGE_TOKEN is required", r.stderr)


def rec(name, seq, sec, prompt=P1, **attrs):
    """One Cowork log record with the documented standard attributes."""
    base = {"session.id": "s-1", "user.account_uuid": "acct-1", "user.email": "alice@example.com",
            "event.name": name, "event.timestamp": f"2026-10-14T18:00:{sec:06.3f}Z", "event.sequence": seq,
            "prompt.id": prompt, **attrs}
    return {"timeUnixNano": "0", "body": {"stringValue": name},
            "attributes": [{"key": k, "value": {"stringValue": str(v)}} for k, v in base.items()]}


def batch(*records, service="cowork"):
    return {"resourceLogs": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
                              "scopeLogs": [{"scope": {"name": "test"}, "logRecords": list(records)}]}]}


if __name__ == "__main__":
    unittest.main()
