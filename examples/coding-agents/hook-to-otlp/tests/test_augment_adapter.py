"""Auggie CLI adapter contract tests against payloads shaped as https://docs.augmentcode.com/cli/hooks documents them.

The fixture turns on every opt-in metadata block Auggie offers
(``context``, ``conversation``, ``mcp_metadata``, ``file_changes``) to prove
the adapter drops them.
"""
from __future__ import annotations

import json
import tempfile
import unittest

from tests.helpers import FIXTURES, attrs, by_name, config, latest, load_jsonl, replay

import emit
from adapters import augment
from adapters.base import SESSION, TURN

SESSION_FIXTURE = FIXTURES / "augment" / "session.jsonl"
SID = "fixture-conv-aug-0001"
MARKERS = ("TOOL_INPUT_MARKER_AUG", "TOOL_OUTPUT_MARKER_AUG", "ERROR_MARKER_AUG")
# Never exported, even with content capture on (R-03, R-04, section 12).
NEVER = ("fixture.user@example.com", "MODEL_LABEL_CANARY", "CONVERSATION_CANARY",
         "FILE_CONTENT_CANARY", "MCP_SERVER_CANARY", "/Users/fixture/project")


class AugmentAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = load_jsonl(SESSION_FIXTURE)

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, capture=False):
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(augment, config("augment", self.tmp.name, **extra), self.records)

    def test_one_trace_keyed_by_conversation_id(self):
        spans = self.spans()
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("augment", SID)})
        root_id = emit.span_id("augment", SID, SESSION, "")
        root = latest(spans, root_id)
        self.assertEqual(root["name"], "Auggie session")
        self.assertEqual(attrs(root)["fi.span.kind"], "AGENT")
        self.assertEqual(attrs(root)["augment.stop.last_cause"], "error")
        children = sorted(s["name"] for s in spans if s.get("parentSpanId") == root_id)
        self.assertEqual(children, ["Agent stop", "Agent stop", "launch-process",
                                    "search_example-server", "str-replace-editor", "view", "view"])
        self.assertFalse([s for s in spans if attrs(s).get("coding_agent.scope") == TURN])

    def test_tools_are_unique_spans_with_status(self):
        spans = self.spans()
        views = by_name(spans, "view")
        self.assertEqual(len({s["spanId"] for s in views}), 2)
        a = attrs(views[0])
        self.assertEqual((a["fi.span.kind"], a["gen_ai.tool.name"], a["augment.tool.is_mcp"]),
                         ("TOOL", "view", False))
        self.assertNotIn("gen_ai.tool.call.id", a)  # Auggie sends no tool call id
        mcp = by_name(spans, "search_example-server")[0]
        self.assertEqual(mcp["status"], {"code": 2, "message": "tool error"})
        self.assertTrue(attrs(mcp)["augment.tool.is_mcp"])
        edit = attrs(by_name(spans, "str-replace-editor")[0])
        self.assertEqual(edit["augment.tool.file_changes.count"], "1")
        self.assertEqual(edit["augment.tool.file_changes.types"], {"values": [{"stringValue": "edit"}]})

    def test_stop_cause_and_error(self):
        stops = by_name(self.spans(), "Agent stop")
        self.assertEqual([attrs(s)["augment.stop.cause"] for s in stops], ["end_turn", "error"])
        self.assertEqual(stops[0]["status"]["code"], 1)
        self.assertEqual(stops[1]["status"], {"code": 2, "message": "agent stopped with error"})

    def test_pre_tool_use_is_not_mapped(self):
        self.assertEqual(augment.parse("PreToolUse", self.records[1]["payload"]), [])

    def test_default_export_has_no_content_or_pii(self):
        encoded = json.dumps(self.spans())
        for marker in MARKERS + NEVER:
            self.assertNotIn(marker, encoded, marker)

    def test_capture_content_opt_in_still_drops_metadata_blocks(self):
        spans = self.spans(capture=True)
        encoded = json.dumps(spans)
        for marker in MARKERS:
            self.assertIn(marker, encoded, marker)
        for marker in NEVER:
            if marker == "/Users/fixture/project":
                continue  # not present in any content field of this fixture either
            self.assertNotIn(marker, encoded, marker)
        mcp = attrs(by_name(spans, "search_example-server")[0])
        self.assertIn("ERROR_MARKER_AUG", mcp["exception.message"])

    def test_missing_conversation_id_is_dropped(self):
        self.assertEqual(augment.parse("PostToolUse", {"tool_name": "view"}), [])


if __name__ == "__main__":
    unittest.main()
