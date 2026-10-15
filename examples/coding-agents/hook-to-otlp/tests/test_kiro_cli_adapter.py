"""Kiro CLI adapter contract tests.

Payloads follow https://kiro.dev/docs/hooks/types/ (CLI V3) and the hook
fields named in the kiro-cli-chat 2.31.1 binary.
"""
from __future__ import annotations

import json
import tempfile
import unittest

from tests.helpers import FIXTURES, attrs, by_name, config, latest, load_jsonl, replay

import emit
from adapters import kiro_cli
from adapters.base import SESSION

SESSION_FIXTURE = FIXTURES / "kiro_cli" / "session.jsonl"
SID = "fixture-kiro-cli-session-0001"
MARKERS = ("PROMPT_MARKER_KIRO_CLI", "TOOL_OUTPUT_MARKER_KIRO_CLI", "ERROR_MARKER_KIRO_CLI",
           "RESPONSE_MARKER_KIRO_CLI")
DEFAULT_ONLY = ("/Users/fixture/project",)


class KiroCliAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = load_jsonl(SESSION_FIXTURE)

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, capture=False, records=None):
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(kiro_cli, config("kiro_cli", self.tmp.name, **extra), records or self.records)

    def test_one_trace_session_turn_tool_tree(self):
        spans = self.spans()
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("kiro_cli", SID)})
        root_id = emit.span_id("kiro_cli", SID, SESSION, "")
        self.assertEqual(latest(spans, root_id)["name"], "Kiro CLI session")
        turns = [s for s in spans if s["name"] == "Kiro CLI turn"]
        self.assertEqual(len({t["spanId"] for t in turns}), 1)
        turn = turns[-1]
        self.assertEqual(turn["parentSpanId"], root_id)
        children = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn["spanId"])
        self.assertEqual(children, ["file_search", "read_file"])

    def test_tools_come_from_post_tool_use_and_failures_are_errors(self):
        spans = self.spans()
        search, = by_name(spans, "file_search")
        read, = by_name(spans, "read_file")
        self.assertEqual(attrs(search)["gen_ai.tool.name"], "file_search")
        self.assertNotIn("kiro.tool.name", attrs(search))
        self.assertNotIn("gen_ai.tool.call.id", attrs(search))
        # Observe-only: no PreToolUse, so no vendor duration.
        self.assertEqual(int(search["endTimeUnixNano"]) - int(search["startTimeUnixNano"]), 0)
        self.assertEqual(search["status"]["code"], 1)
        self.assertEqual(read["status"], {"code": 2, "message": "tool reported failure"})

    def test_pre_tool_use_is_not_mapped(self):
        payload = {"session_id": "s", "tool_name": "read_file", "tool_input": {"path": "/tmp/a"}}
        for event in ("PreToolUse", "preToolUse"):
            self.assertEqual(kiro_cli.parse(event, payload), [])

    def test_agent_spawn_and_cli2_names_are_accepted(self):
        renamed = {"SessionStart": "agentSpawn", "UserPromptSubmit": "userPromptSubmit",
                   "PostToolUse": "postToolUse", "Stop": "stop"}
        records = []
        for record in self.records:
            event = renamed.get(record["event"], record["event"])
            records.append({"event": event, "payload": {**record["payload"], "hook_event_name": event}})
        spans = self.spans(records=records)
        self.assertEqual(sorted({s["name"] for s in spans}),
                         ["Kiro CLI session", "Kiro CLI turn", "file_search", "read_file"])
        root = latest(spans, emit.span_id("kiro_cli", SID, SESSION, ""))
        self.assertEqual(attrs(root)["kiro.hook.trigger"], "agentSpawn")
        # The 2.x spelling is recorded on every span it produced.
        self.assertEqual(attrs(by_name(spans, "file_search")[0])["kiro.hook.trigger"], "postToolUse")
        self.assertEqual(attrs([s for s in spans if s["name"] == "Kiro CLI turn"][-1])["kiro.hook.trigger"], "stop")

    def test_default_export_has_no_content_or_paths(self):
        encoded = json.dumps(self.spans())
        for marker in MARKERS + DEFAULT_ONLY:
            self.assertNotIn(marker, encoded, marker)

    def test_opt_in_exports_prompt_tools_and_response(self):
        spans = self.spans(capture=True)
        encoded = json.dumps(spans)
        for marker in MARKERS:
            self.assertIn(marker, encoded, marker)
        turn = [s for s in spans if s["name"] == "Kiro CLI turn"][-1]
        self.assertIn("RESPONSE_MARKER_KIRO_CLI", attrs(turn)["output.value"])

    def test_ide_only_and_unknown_triggers_are_ignored(self):
        payload = {"session_id": "s", "cwd": "/x", "file_path": "/x/a.ts"}
        for event in ("PostFileSave", "PreTaskExec", "Manual", "BeforeTool", ""):
            self.assertEqual(kiro_cli.parse(event, payload), [])

    def test_missing_session_id_drops_event(self):
        payload = dict(self.records[2]["payload"])
        del payload["session_id"]
        self.assertEqual(kiro_cli.parse("PostToolUse", payload), [])

    def test_session_end_keeps_state_so_a_resumed_session_continues(self):
        cfg = config("kiro_cli", self.tmp.name)
        first = replay(kiro_cli, cfg, self.records)  # ends with SessionEnd
        root_id = emit.span_id("kiro_cli", SID, SESSION, "")
        first_root = latest(first, root_id)
        # kiro-cli chat --resume-id <session_id> continues the same session id.
        resumed = replay(kiro_cli, cfg, [
            {"event": "UserPromptSubmit", "payload": {"session_id": SID, "prompt": "second"}},
            {"event": "PostToolUse", "payload": {"session_id": SID, "tool_name": "read_file",
                                                 "tool_response": {"success": True}}},
            {"event": "Stop", "payload": {"session_id": SID}},
        ])
        turn_ids = {s["spanId"] for s in first + resumed if s["name"] == "Kiro CLI turn"}
        self.assertEqual(turn_ids, {emit.span_id("kiro_cli", SID, "turn", "turn-1"),
                                    emit.span_id("kiro_cli", SID, "turn", "turn-2")})
        self.assertEqual(latest(resumed, root_id)["startTimeUnixNano"], first_root["startTimeUnixNano"])

    def test_session_end_closes_a_turn_interrupted_before_stop(self):
        records = self.records[:3] + [self.records[-1]]  # Ctrl+C: no Stop, then SessionEnd
        spans = self.spans(records=records)
        turn = [s for s in spans if s["name"] == "Kiro CLI turn"][-1]
        self.assertEqual(attrs(turn)["kiro.turn.ended_by"], "SessionEnd")
        tool, = by_name(spans, "file_search")
        self.assertEqual(tool["parentSpanId"], turn["spanId"])

    def test_error_text_with_paths_is_not_exported_by_default(self):
        failure = {"success": False, "result": ["open /Users/alice.smith/secret/app.py: permission denied"]}
        records = self.records[:2] + [{"event": "PostToolUse", "payload": {
            "session_id": SID, "tool_name": "execute_bash", "tool_input": {"command": "cat /Users/alice.smith/x"},
            "tool_response": failure}}]
        encoded = json.dumps(self.spans(records=records))
        self.assertNotIn("alice.smith", encoded)
        self.assertNotIn("/Users/", encoded)
        self.assertIn("tool reported failure", encoded)

    def test_stdout_adds_nothing_to_agent_context(self):
        for event in ("SessionStart", "UserPromptSubmit", "Stop"):
            self.assertEqual(kiro_cli.respond(event, {}), "")


if __name__ == "__main__":
    unittest.main()
