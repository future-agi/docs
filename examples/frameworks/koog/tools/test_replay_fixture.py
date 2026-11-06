"""Offline checks for the recorded Koog fixture and the replay script. Run: python3 -m unittest -v"""
import contextlib
import io
import os
import unittest

import replay_fixture as rf

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "koog-1.3.0-weather.otlp.json")
CONTENT_KEYS = {
    "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions", "system_instructions",
    "gen_ai.tool.definitions", "gen_ai.tool.call.arguments", "gen_ai.tool.call.result",
    "koog.node.input", "koog.node.output", "koog.subgraph.input", "koog.subgraph.output",
}


def attrs(span):
    return {a["key"]: next(iter(a["value"].values())) for a in span.get("attributes", [])}


class FixtureShape(unittest.TestCase):
    def setUp(self):
        self.requests = rf.load(FIXTURE)
        self.spans = list(rf.spans_of(self.requests))

    def test_recorded_span_tree(self):
        names = [s["name"] for s in self.spans]
        for prefix in ("create_agent ", "invoke_agent ", "strategy single_run", "node nodeCallLLM", "chat ", "execute_tool getWeather"):
            self.assertTrue(any(n.startswith(prefix) for n in names), prefix)
        self.assertEqual(1, len({s["traceId"] for s in self.spans}))
        ids = {s["spanId"] for s in self.spans}
        roots = [s for s in self.spans if not s.get("parentSpanId")]
        self.assertEqual(["create_agent"], [r["name"].split()[0] for r in roots])
        for s in self.spans:
            if s.get("parentSpanId"):
                self.assertIn(s["parentSpanId"], ids, "dangling parent for " + s["name"])

    def test_model_tokens_session_kind(self):
        chats = [s for s in self.spans if s["name"].startswith("chat ")]
        self.assertEqual(2, len(chats))
        for c in chats:
            a = attrs(c)
            self.assertTrue(a.get("gen_ai.request.model"))
            self.assertTrue(int(a["gen_ai.usage.input_tokens"]) > 0)
            self.assertEqual("fixture-session", a.get("session.id"))
        kinds = {s["name"].split()[0]: attrs(s).get("fi.span.kind") for s in self.spans}
        self.assertEqual("AGENT", kinds["invoke_agent"])
        self.assertEqual("CHAIN", kinds["strategy"])

    def test_content_is_masked_and_resource_is_clean(self):
        for s in self.spans:
            for k, v in attrs(s).items():
                if k in CONTENT_KEYS:
                    self.assertIn(v, ("HIDDEN:non-empty", ""), k)
            self.assertEqual([], s.get("events", []))
        for req in self.requests:
            for rs in req["resourceSpans"]:
                keys = {a["key"] for a in rs["resource"]["attributes"]}
                self.assertIn("project_name", keys)
                self.assertFalse(keys & {"host.name", "process.command_line", "process.owner", "user.name"})


class Restamp(unittest.TestCase):
    def test_new_ids_keep_links_and_project(self):
        before = rf.load(FIXTURE)
        after, traces = rf.restamp(before, "replay-project", now_ns=2_000_000_000_000_000_000)
        old, new = list(rf.spans_of(before)), list(rf.spans_of(after))
        self.assertEqual(1, len(traces))
        self.assertTrue(all(o["spanId"] != n["spanId"] for o, n in zip(old, new)))
        old_parent = {o["name"]: next((p["name"] for p in old if p["spanId"] == o.get("parentSpanId")), None) for o in old}
        new_parent = {n["name"]: next((p["name"] for p in new if p["spanId"] == n.get("parentSpanId")), None) for n in new}
        self.assertEqual(old_parent, new_parent)
        self.assertEqual(2_000_000_000_000_000_000, max(int(s["endTimeUnixNano"]) for s in new))
        for rs in (r for req in after for r in req["resourceSpans"]):
            vals = [a["value"]["stringValue"] for a in rs["resource"]["attributes"] if a["key"] == "project_name"]
            self.assertEqual(["replay-project"], vals)

    def test_dry_run_sends_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, rf.main([FIXTURE, "--project", "p", "--dry-run", "--base-url", "http://127.0.0.1:9"]))
        self.assertIn('"project_name"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
