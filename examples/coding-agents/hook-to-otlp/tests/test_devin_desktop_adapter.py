"""Devin Desktop Cascade adapter contract tests against payloads shaped as https://docs.devin.ai/desktop/cascade/hooks documents them."""
from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import unittest
from unittest import mock

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
        self.assertEqual((mcp["fi.span.kind"], mcp["devin_desktop.mcp.server"], mcp["coding_agent.hook.event"]),
                         ("TOOL", "github", "post_mcp_tool_use"))
        write = attrs(by_name(spans, "write_code")[0])
        self.assertEqual(write["devin_desktop.write.edit_count"], "1")
        self.assertEqual(write["coding_agent.turn.id"], "fixture-exec-0001")
        self.assertEqual(write["devin_desktop.model_label"], "Claude Sonnet 4")
        self.assertNotIn("devin_desktop.action", write)  # duplicates coding_agent.hook.event

    def test_tool_status(self):
        spans = self.spans()
        # Read, write and MCP hooks fire after a successful action; a command's outcome is unknown.
        for name in ("read_code", "write_code", "list_commits"):
            self.assertEqual(by_name(spans, name)[0]["status"], {"code": 1}, name)
        for span in by_name(spans, "run_command"):
            self.assertEqual(span["status"], {"code": 0})

    def test_respond_prints_nothing(self):
        for record in self.records:
            self.assertEqual(devin_desktop.respond(record["event"], record["payload"]), "")

    def test_stale_state_of_old_conversations_is_swept(self):
        cfg = config("devin_desktop", self.tmp.name, FI_HOOK_STATE_TTL_HOURS="0")
        replay(devin_desktop, cfg, self.records)
        old_state = cfg.state_dir / (emit._hex("state", "devin_desktop", SID, length=32) + ".json")
        self.assertTrue(old_state.exists())
        second = dict(self.records[0], payload=dict(self.records[0]["payload"], trajectory_id="fixture-traj-0002"))
        replay(devin_desktop, cfg, [second])
        self.assertFalse(old_state.exists())

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
        # Paths inside opted-in tool input keep the path but not the account name.
        self.assertIn("/Users/<user>/project", encoded)
        self.assertNotIn("/Users/fixture/", encoded)

    def test_error_text_with_path_and_user_is_content(self):
        # An MCP tool error comes back in mcp_result; a command line can name a home path.
        records = [
            {"event": "pre_user_prompt", "payload": {"agent_action_name": "pre_user_prompt", "trajectory_id": "err-traj",
                                                     "execution_id": "err-exec", "tool_info": {"user_prompt": "p"}}},
            {"event": "post_mcp_tool_use", "payload": {
                "agent_action_name": "post_mcp_tool_use", "trajectory_id": "err-traj", "execution_id": "err-exec",
                "tool_info": {"mcp_server_name": "fs", "mcp_tool_name": "read_file",
                              "mcp_tool_arguments": {"path": "/Users/alice-canary/secret.txt"},
                              "mcp_result": "Error: ENOENT: no such file '/Users/alice-canary/secret.txt'"}}},
            {"event": "post_run_command", "payload": {
                "agent_action_name": "post_run_command", "trajectory_id": "err-traj", "execution_id": "err-exec",
                "tool_info": {"command_line": "cat /home/alice-canary/.netrc", "cwd": "/home/alice-canary/repo"}}},
            {"event": "post_cascade_response", "payload": {"agent_action_name": "post_cascade_response",
                                                           "trajectory_id": "err-traj", "execution_id": "err-exec",
                                                           "tool_info": {"response": "r"}}},
        ]
        default = json.dumps(replay(devin_desktop, config("devin_desktop", self.tmp.name), records))
        for text in ("alice-canary", "ENOENT", "/Users/", "/home/"):
            self.assertNotIn(text, default, text)
        with tempfile.TemporaryDirectory() as tmp:
            opted = json.dumps(replay(devin_desktop, config("devin_desktop", tmp, FI_HOOK_CAPTURE_CONTENT="1"), records))
        self.assertIn("ENOENT", opted)
        self.assertIn("/Users/<user>/secret.txt", opted)
        self.assertNotIn("alice-canary", opted)  # user name scrubbed, cwd never captured

    def test_transcript_path_is_never_opened(self):
        opened = []

        def spy(real):
            def wrapper(path, *args, **kwargs):
                opened.append(str(path))
                return real(path, *args, **kwargs)
            return wrapper

        with mock.patch("builtins.open", spy(builtins.open)), mock.patch("io.open", spy(io.open)), \
                mock.patch("os.open", spy(os.open)):
            self.spans(capture=True)
        self.assertTrue(opened)  # the spies saw the state file
        self.assertFalse([p for p in opened if "CANARY" in p], opened)

    def test_hosted_devin_payload_is_not_a_cascade_event(self):
        payload = json.loads(HOSTED_FIXTURE.read_text())
        for event in (None, "post_cascade_response", "pre_user_prompt"):
            self.assertEqual(devin_desktop.parse(event or "", payload), [])

    def test_skipped_turn_end_is_closed_by_next_prompt(self):
        # Drop the first post_cascade_response, as a cancelled turn would.
        first_end = next(i for i, r in enumerate(self.records) if r["event"] == "post_cascade_response")
        records = self.records[:first_end] + self.records[first_end + 1:]
        spans = replay(devin_desktop, config("devin_desktop", self.tmp.name), records)
        turn1_id = emit.span_id("devin_desktop", SID, TURN, "fixture-exec-0001")
        turn1 = latest(spans, turn1_id)
        self.assertIsNotNone(turn1)
        self.assertTrue(attrs(turn1)["coding_agent.incomplete"])
        exported = {s["spanId"] for s in spans}
        orphans = [s["name"] for s in spans if s.get("parentSpanId") and s["parentSpanId"] not in exported]
        self.assertEqual(orphans, [])

    def test_missing_trajectory_is_dropped(self):
        self.assertEqual(devin_desktop.parse("post_read_code", {"execution_id": "x", "tool_info": {}}), [])


if __name__ == "__main__":
    unittest.main()
