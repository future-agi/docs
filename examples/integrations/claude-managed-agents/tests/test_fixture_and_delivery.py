"""Offline tests for the synthetic API-span fixture and the delivery emulator.

Run: python -I tests/test_fixture_and_delivery.py   (needs opentelemetry-proto)
"""
import gzip
import json
import pathlib
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "spike"))
from deliver import deliver_like_claude_platform  # noqa: E402
from fixture import add_project_name, build  # noqa: E402
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest  # noqa: E402

# Span names and gen_ai.operation.name values from
# https://platform.claude.com/docs/en/api/opentelemetry/spans (read 2026-10-16)
DOCUMENTED = {
    "anthropic.sessions.events.send": None,
    "anthropic.session.turn": "invoke_agent",
    "anthropic.model_request": "chat",
    "anthropic.tool_use bash": "execute_tool",
}
CONTENT_KEYS = {"gen_ai.system_instructions", "gen_ai.input.messages", "gen_ai.output.messages",
                "gen_ai.tool.call.arguments", "anthropic.tool_result.content"}
MARK = "UNITTESTMARKER123"


def spans_of(req):
    rs = req.resource_spans[0]
    return rs, rs.scope_spans[0].spans


def attrs(span):
    return {a.key: (a.value.string_value or a.value.int_value) for a in span.attributes}


class Fixture(unittest.TestCase):
    def test_resource_and_scope_match_anthropic(self):
        rs, _ = spans_of(build("metadata_only", MARK)[0])
        res = {a.key: a.value.string_value for a in rs.resource.attributes}
        self.assertEqual(res, {"service.name": "claude-platform"})  # no project_name: Anthropic cannot set one
        self.assertEqual(rs.scope_spans[0].scope.name, "com.anthropic.claude-platform")

    def test_names_kinds_operations_and_parents(self):
        _, spans = spans_of(build("metadata_only", MARK)[0])
        by_name = {}
        for s in spans:
            by_name.setdefault(s.name, []).append(s)
        self.assertEqual(set(by_name), set(DOCUMENTED))
        for name, op in DOCUMENTED.items():
            for s in by_name[name]:
                self.assertEqual(attrs(s).get("gen_ai.operation.name"), op)
        send = by_name["anthropic.sessions.events.send"][0]
        turn = by_name["anthropic.session.turn"][0]
        self.assertEqual(send.kind, send.SPAN_KIND_SERVER)
        self.assertEqual(turn.parent_span_id, send.span_id)
        for s in by_name["anthropic.model_request"] + by_name["anthropic.tool_use bash"]:
            self.assertEqual(s.parent_span_id, turn.span_id)
            self.assertEqual(s.kind, s.SPAN_KIND_INTERNAL)
        self.assertEqual(len(by_name["anthropic.model_request"]), 2)
        self.assertEqual(attrs(by_name["anthropic.model_request"][0])["gen_ai.usage.input_tokens"], 1834)

    def test_metadata_only_has_no_content_and_no_marker(self):
        req, _ = build("metadata_only", MARK)
        _, spans = spans_of(req)
        for s in spans:
            self.assertFalse(CONTENT_KEYS & set(attrs(s)), s.name)
        self.assertNotIn(MARK.encode(), req.SerializeToString())

    def test_content_mode_marker_only_in_content_keys(self):
        req, _ = build("content", MARK)
        _, spans = spans_of(req)
        seen = set()
        for s in spans:
            for k, v in attrs(s).items():
                if MARK in str(v):
                    self.assertIn(k, CONTENT_KEYS)
                    seen.add(k)
        self.assertEqual(seen, CONTENT_KEYS)

    def test_failure_trace_is_error(self):
        _, spans = spans_of(build("metadata_only", MARK, failure=True)[0])
        errs = [s for s in spans if s.status.code == s.status.STATUS_CODE_ERROR]
        self.assertEqual({s.name for s in errs}, {"anthropic.session.turn", "anthropic.model_request"})
        self.assertTrue(all(attrs(s)["error.type"] == "rate_limit_error" for s in errs))

    def test_add_project_name_is_idempotent_and_copy(self):
        req, _ = build("metadata_only", MARK)
        out = add_project_name(add_project_name(req, "p1"), "p2")
        res = [a for a in out.resource_spans[0].resource.attributes if a.key == "project_name"]
        self.assertEqual([a.value.string_value for a in res], ["p1"])
        self.assertFalse(any(a.key == "project_name" for a in req.resource_spans[0].resource.attributes))


class _Endpoint(BaseHTTPRequestHandler):
    gzip_status = 400
    seen: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        enc = self.headers.get("Content-Encoding")
        if enc == "gzip":
            body = gzip.decompress(body)
        ExportTraceServiceRequest.FromString(body)  # must be valid OTLP protobuf
        type(self).seen.append((enc, self.headers.get("User-Agent"), self.headers.get("X-Api-Key")))
        code = type(self).gzip_status if enc == "gzip" else 200
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()


class Delivery(unittest.TestCase):
    def run_with(self, gzip_status):
        _Endpoint.gzip_status, _Endpoint.seen = gzip_status, []
        srv = HTTPServer(("127.0.0.1", 0), _Endpoint)
        t = threading.Thread(target=srv.handle_request if gzip_status == 200 else srv.serve_forever, daemon=True)
        t.start()
        try:
            payload = build("metadata_only", MARK)[0].SerializeToString()
            return deliver_like_claude_platform(f"http://127.0.0.1:{srv.server_port}/v1/traces", payload,
                                                {"X-Api-Key": "k"}), list(_Endpoint.seen)
        finally:
            if gzip_status != 200:
                srv.shutdown()
            srv.server_close()

    def test_gzip_rejected_with_400_is_resent_uncompressed(self):
        res, seen = self.run_with(400)
        self.assertTrue(res["delivered"])
        self.assertEqual([s[0] for s in seen], ["gzip", None])
        self.assertTrue(all(s[1] == "Claude-Platform" and s[2] == "k" for s in seen))

    def test_415_also_triggers_resend(self):
        res, seen = self.run_with(415)
        self.assertTrue(res["delivered"])
        self.assertEqual(len(seen), 2)

    def test_other_status_is_not_resent(self):
        res, seen = self.run_with(500)
        self.assertFalse(res["delivered"])
        self.assertEqual(len(seen), 1)

    def test_gzip_accepted_needs_no_resend(self):
        res, seen = self.run_with(200)
        self.assertTrue(res["delivered"])
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
