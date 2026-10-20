"""Auggie CLI adapter contract tests against payloads shaped as https://docs.augmentcode.com/cli/hooks documents them.

The fixture turns on every opt-in metadata block Auggie offers
(``context``, ``conversation``, ``mcp_metadata``, ``file_changes``) and adds
the two undocumented fields the 0.36.0 bundle can put in the hook input
(``user_prompt`` on tool events, ``_exchange`` on ``Stop``), to prove the
adapter drops them. The MCP tool follows Augment's ``<tool>_<server>``
naming, so the server name is (by design) part of the exported tool name.
"""
from __future__ import annotations

import json
import tempfile
import unittest

from tests.helpers import FIXTURES, attrs, by_name, config, latest, load_jsonl, replay

import emit
from adapters import augment
from adapters.base import ERROR, OK, SESSION, TURN

SESSION_FIXTURE = FIXTURES / "augment" / "session.jsonl"
SID = "fixture-conv-aug-0001"
MARKERS = ("TOOL_INPUT_MARKER_AUG", "TOOL_OUTPUT_MARKER_AUG", "ERROR_MARKER_AUG")
# Never exported, even with content capture on (R-03, R-04, section 12).
NEVER = ("fixture.user@example.com", "MODEL_LABEL_CANARY", "CONVERSATION_CANARY",
         "FILE_CONTENT_CANARY", "PROMPT_CANARY_AUG", "EXCHANGE_CANARY", "/Users/fixture/project")
# tool_error text in the fixture: a home path with a user name.
ERROR_USER = "fixtureuser"
MCP_TOTAL_TOOLS = 7319  # mcp_metadata.mcpTotalToolsCount in the fixture


def all_attribute_values(spans):
    for span in spans:
        for item in span.get("attributes", []):
            yield item["key"], next(iter(item["value"].values()))


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

    def test_every_0_36_0_stop_cause_is_recorded_as_is(self):
        # 0.36.0 enum: interrupted, end_turn, max_iterations, empty_completion (undocumented), error.
        for cause in ("interrupted", "end_turn", "max_iterations", "empty_completion", "error"):
            stop, update = augment.parse("Stop", {"hook_event_name": "Stop", "conversation_id": SID,
                                                  "agent_stop_cause": cause})
            self.assertEqual(stop.attributes, {"augment.stop.cause": cause})
            self.assertEqual(stop.status, ERROR if cause == "error" else OK, cause)
            self.assertEqual(update.attributes, {"augment.stop.last_cause": cause})

    def test_pre_tool_use_is_not_mapped(self):
        self.assertEqual(augment.parse("PreToolUse", self.records[1]["payload"]), [])

    def test_default_export_has_no_content_or_pii(self):
        spans = self.spans()
        encoded = json.dumps(spans)
        for marker in MARKERS + NEVER + (ERROR_USER, "/Users/"):
            self.assertNotIn(marker, encoded, marker)

    def test_error_text_with_a_path_and_user_name_is_content(self):
        mcp = by_name(self.spans(), "search_example-server")[0]
        self.assertEqual(mcp["status"]["message"], "tool error")  # fixed text, never the error
        self.assertNotIn("exception.message", attrs(mcp))
        captured = attrs(by_name(self.spans(capture=True), "search_example-server")[0])
        self.assertIn("ERROR_MARKER_AUG permission denied: /Users/<user>/project/.env", captured["exception.message"])
        self.assertNotIn(ERROR_USER, json.dumps(captured))

    def test_mcp_server_is_only_in_the_tool_name(self):
        # Augment names MCP tools <tool>_<server>: the server name goes out in the tool name,
        # nothing else from mcp_metadata does.
        for capture in (False, True):
            spans = self.spans(capture=capture)
            mcp = attrs(by_name(spans, "search_example-server")[0])
            self.assertEqual(mcp["gen_ai.tool.name"], "search_example-server")
            for key, value in all_attribute_values(spans):
                self.assertNotIn("mcp_metadata", key)
                self.assertNotIn(str(MCP_TOTAL_TOOLS), str(value), key)
                if key not in ("gen_ai.tool.name", "augment.tool.name", "input.value"):
                    self.assertNotIn("example-server", str(value), key)

    def test_capture_content_opt_in_still_drops_metadata_blocks(self):
        spans = self.spans(capture=True)
        encoded = json.dumps(spans)
        for marker in MARKERS:
            self.assertIn(marker, encoded, marker)
        for marker in NEVER:
            self.assertNotIn(marker, encoded, marker)
        mcp = attrs(by_name(spans, "search_example-server")[0])
        self.assertIn("ERROR_MARKER_AUG", mcp["exception.message"])

    def test_missing_conversation_id_is_dropped(self):
        self.assertEqual(augment.parse("PostToolUse", {"tool_name": "view"}), [])


if __name__ == "__main__":
    unittest.main()
