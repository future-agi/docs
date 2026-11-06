#!/usr/bin/env python3
"""Contract test for the goose OTLP recipe.

The fixtures under fixtures/ were recorded from real goose 1.54.0 CLI runs
(`goose run` with the developer extension, one prompt that listed files and
read README.md) exporting to record_otlp.py: OpenAI-compatible provider with
content off (default) and on (content), and the Anthropic provider with
content off (anthropic). They hold span names, parents,
and attribute keys only; no prompt, tool, or result text.

These tests pin what the recipe promises:
  * one trace per `goose run`, rooted at `reply`;
  * model calls and tool calls are child spans with gen_ai.* structure;
  * with OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT unset, no content
    attribute is exported; with it set to true, content attributes appear.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import record_otlp  # noqa: E402

DEFAULT = json.loads((ROOT / "fixtures" / "goose-1.54.0-default.json").read_text())
CONTENT = json.loads((ROOT / "fixtures" / "goose-1.54.0-content.json").read_text())
ANTHROPIC = json.loads((ROOT / "fixtures" / "goose-1.54.0-anthropic.json").read_text())


def by_name(fixture: dict, name: str) -> list[dict]:
    return [s for s in fixture["spans"] if s["name"] == name]


class SpanTreeContract(unittest.TestCase):
    def test_one_trace_rooted_at_reply(self):
        for fixture in (DEFAULT, CONTENT, ANTHROPIC):
            self.assertEqual(fixture["trace_count"], 1)
            roots = [s for s in fixture["spans"] if not s["parent"]]
            self.assertEqual([r["name"] for r in roots], ["reply"])
            self.assertEqual(roots[0]["attributes"]["gen_ai.operation.name"], "invoke_agent")

    def test_model_and_tool_spans_hang_off_reply_stream(self):
        (stream,) = by_name(DEFAULT, "reply_stream")
        self.assertEqual(stream["parent"], "reply")
        chats = by_name(DEFAULT, "stream_response_from_provider")
        tools = by_name(DEFAULT, "dispatch_tool_call")
        self.assertGreaterEqual(len(chats), 1)
        self.assertGreaterEqual(len(tools), 1)
        for span in chats:
            self.assertEqual(span["parent"], "reply_stream")
            self.assertEqual(span["attributes"]["gen_ai.operation.name"], "chat")
            for key in ("gen_ai.request.model", "gen_ai.provider.name",
                        "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"):
                self.assertIn(key, span["attributes"])
        for span in tools:
            self.assertEqual(span["parent"], "reply_stream")
            self.assertEqual(span["attributes"]["gen_ai.operation.name"], "execute_tool")
            self.assertIn("gen_ai.tool.call.id", span["attributes"])
            self.assertTrue(span["attributes"]["gen_ai.tool.name"])

    def test_provider_swap_keeps_the_same_tree(self):
        def shape(fixture):
            return sorted({(s["name"], s["parent"], s["attributes"].get("gen_ai.operation.name"))
                           for s in fixture["spans"]})
        self.assertEqual(shape(DEFAULT), shape(ANTHROPIC))
        providers = {s["attributes"].get("gen_ai.provider.name") for s in by_name(ANTHROPIC, "stream_response_from_provider")}
        self.assertEqual(providers, {"anthropic"})

    def test_every_span_carries_session_id(self):
        for span in DEFAULT["spans"]:
            self.assertIn("session.id", span["attributes"], span["name"])

    def test_goose_identifies_itself_as_the_service(self):
        # project_name and project_type are added by the collector, not goose;
        # test_collector.py checks them.
        for fixture in (DEFAULT, CONTENT, ANTHROPIC):
            self.assertIn("service.name", fixture["resource_attribute_keys"])


class PrivacyContract(unittest.TestCase):
    def test_default_run_exports_no_content(self):
        for span in DEFAULT["spans"] + ANTHROPIC["spans"]:
            leaked = record_otlp.CONTENT_KEYS & span["attributes"].keys()
            self.assertFalse(leaked, f"{span['name']} exported {sorted(leaked)}")

    def test_opt_in_run_exports_content(self):
        exported = set()
        for span in CONTENT["spans"]:
            exported |= record_otlp.CONTENT_KEYS & span["attributes"].keys()
        self.assertIn("gen_ai.input.messages", exported)
        self.assertIn("gen_ai.tool.call.arguments", exported)
        self.assertIn("gen_ai.tool.call.result", exported)

    def test_every_content_only_key_is_classified_as_content(self):
        default_keys = {k for s in DEFAULT["spans"] for k in s["attributes"]}
        content_keys = {k for s in CONTENT["spans"] for k in s["attributes"]}
        self.assertLessEqual(content_keys - default_keys, record_otlp.CONTENT_KEYS)

    def test_fixtures_hold_no_values_outside_the_allowlist(self):
        for fixture in (DEFAULT, CONTENT, ANTHROPIC):
            for span in fixture["spans"]:
                for key, value in span["attributes"].items():
                    if key not in record_otlp.KEEP_VALUES:
                        self.assertEqual(value, "<present>", key)


class RecorderSummary(unittest.TestCase):
    """summarize() must drop values that are not on the allowlist."""

    @classmethod
    def setUpClass(cls):
        try:
            from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("pip install opentelemetry-proto to test record_otlp.summarize")
        cls.pb = trace_service_pb2

    def test_summary_strips_content_values(self):
        req = self.pb.ExportTraceServiceRequest()
        rs = req.resource_spans.add()
        kv = rs.resource.attributes.add()
        kv.key, kv.value.string_value = "user.name", "alice"
        span = rs.scope_spans.add().spans.add()
        span.trace_id, span.span_id, span.name = b"\x01" * 16, b"\x02" * 8, "dispatch_tool_call"
        for key, value in (("gen_ai.tool.name", "shell"),
                           ("gen_ai.tool.call.arguments", '{"command": "cat SECRET-123"}')):
            attr = span.attributes.add()
            attr.key, attr.value.string_value = key, value
        summary = record_otlp.summarize([req])
        self.assertNotIn("SECRET-123", json.dumps(summary))
        self.assertNotIn("alice", json.dumps(summary))
        (out,) = summary["spans"]
        self.assertEqual(out["attributes"]["gen_ai.tool.name"], "shell")
        self.assertEqual(out["attributes"]["gen_ai.tool.call.arguments"], "<present>")
        self.assertEqual(out["parent"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
