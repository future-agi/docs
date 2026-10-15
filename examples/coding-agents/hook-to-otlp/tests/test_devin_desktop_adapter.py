"""Devin Desktop Cascade adapter contract tests against payloads shaped as https://docs.devin.ai/desktop/cascade/hooks documents them."""
from __future__ import annotations

import builtins
import json
import tempfile
import unittest

from tests.helpers import FIXTURES, attrs, by_name, config, latest, load_jsonl, replay

import emit
from adapters import devin_desktop
from adapters.base import SESSION, TURN

SESSION_FIXTURE = FIXTURES / "devin_desktop" / "session.jsonl"
HOSTED_FIXTURE = FIXTURES / "devin_desktop" / "hosted_insights.json"
SID = "fixture-traj-0001"
MARKERS = ("PROMPT_MARKER_CASCADE", "TOOL_INPUT_MARKER_CASCADE", "TOOL_OUTPUT_MARKER_CASCADE",
           "RESPONSE_MARKER_CASCADE")
# Never exported, even with content capture on.
NEVER = ("fixture-transcript-CANARY", "WORKTREE_CANARY")
# Paths only appear inside opted-in content, never as metadata.
DEFAULT_ONLY = ("/Users/fixture/project",)


class DevinDesktopAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = load_jsonl(SESSION_FIXTURE)

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, capture=False):
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(devin_desktop, config("devin_desktop", self.tmp.name, **extra), self.records)

    def test_one_trace_per_trajectory_with_turns_and_tools(self):
        spans = self.spans()
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("devin_desktop", SID)})
        root_id = emit.span_id("devin_desktop", SID, SESSION, "")
        root = latest(spans, root_id)
        self.assertEqual(root["name"], "Cascade session")
        self.assertEqual(attrs(root)["llm.model_name"], "Claude Sonnet 4")
        turn1_id = emit.span_id("devin_desktop", SID, TURN, "fixture-exec-0001")
        turn1 = latest(spans, turn1_id)
        self.assertEqual(turn1["name"], "Cascade turn")
        self.assertEqual(turn1["parentSpanId"], root_id)
        self.assertEqual(attrs(turn1)["devin_desktop.model_label"], "Claude Sonnet 4")
        names = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn1_id)
        self.assertEqual(names, ["list_commits", "read_code", "run_command", "write_code"])
        turn2_id = emit.span_id("devin_desktop", SID, TURN, "fixture-exec-0002")
        self.assertEqual([s["name"] for s in spans if s.get("parentSpanId") == turn2_id], ["run_command"])
        self.assertNotIn("devin_desktop.model_label", attrs(latest(spans, turn2_id)))  # "Unknown" dropped

    def test_tool_metadata(self):
        spans = self.spans()
        mcp = attrs(by_name(spans, "list_commits")[0])
        self.assertEqual((mcp["fi.span.kind"], mcp["devin_desktop.mcp.server"], mcp["devin_desktop.action"]),
                         ("TOOL", "github", "post_mcp_tool_use"))
        write = attrs(by_name(spans, "write_code")[0])
        self.assertEqual(write["devin_desktop.write.edit_count"], "1")
        self.assertEqual(write["devin_desktop.execution_id"], "fixture-exec-0001")

    def test_pre_hooks_transcript_and_worktree_are_not_mapped(self):
        for record in self.records:
            if record["event"] in ("pre_read_code", "pre_run_command",
                                   "post_cascade_response_with_transcript", "post_setup_worktree"):
                self.assertEqual(devin_desktop.parse(record["event"], record["payload"]), [], record["event"])

    def test_default_export_has_no_content_or_paths(self):
        encoded = json.dumps(self.spans())
        for marker in MARKERS + NEVER + DEFAULT_ONLY:
            self.assertNotIn(marker, encoded, marker)

    def test_capture_content_opt_in(self):
        spans = self.spans(capture=True)
        encoded = json.dumps(spans)
        for marker in MARKERS:
            self.assertIn(marker, encoded, marker)
        for marker in NEVER:
            self.assertNotIn(marker, encoded, marker)

    def test_transcript_path_is_never_opened(self):
        real_open = builtins.open
        opened = []

        def guard(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        builtins.open = guard
        try:
            self.spans(capture=True)
        finally:
            builtins.open = real_open
        self.assertFalse([p for p in opened if "CANARY" in p], opened)

    def test_hosted_devin_payload_is_not_a_cascade_event(self):
        payload = json.loads(HOSTED_FIXTURE.read_text())
        for event in (None, "post_cascade_response", "pre_user_prompt"):
            self.assertEqual(devin_desktop.parse(event or "", payload), [])

    def test_missing_trajectory_is_dropped(self):
        self.assertEqual(devin_desktop.parse("post_read_code", {"execution_id": "x", "tool_info": {}}), [])


if __name__ == "__main__":
    unittest.main()
