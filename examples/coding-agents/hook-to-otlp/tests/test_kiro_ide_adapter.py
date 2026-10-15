"""Kiro IDE adapter contract tests.

Payloads follow https://kiro.dev/docs/hooks/types/ and the payload builder in
the Kiro IDE 1.2.37 ``kiro.kiro-agent`` extension.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import unittest

from tests.helpers import FIXTURES, attrs, by_name, config, latest, load_jsonl, replay

import emit
from adapters import kiro_ide
from adapters.base import SESSION

SESSION_FIXTURE = FIXTURES / "kiro_ide" / "session.jsonl"
SID = "fixture-kiro-ide-session-0001"
MARKERS = ("PROMPT_MARKER_KIRO_IDE", "TOOL_INPUT_MARKER_KIRO_IDE", "TOOL_OUTPUT_MARKER_KIRO_IDE",
           "ERROR_MARKER_KIRO_IDE", "SPEC_MARKER_KIRO_IDE")
# Paths only appear inside opted-in content (tool input, file events), never as metadata.
DEFAULT_ONLY = ("/Users/fixture/project",)


class KiroIdeAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = load_jsonl(SESSION_FIXTURE)

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, capture=False):
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(kiro_ide, config("kiro_ide", self.tmp.name, **extra), self.records)

    def test_one_trace_session_turn_tool_tree(self):
        spans = self.spans()
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("kiro_ide", SID)})
        root_id = emit.span_id("kiro_ide", SID, SESSION, "")
        root = latest(spans, root_id)
        self.assertEqual(root["name"], "Kiro IDE session")
        self.assertNotIn("kiro.session.end_reason", attrs(root))
        turns = [s for s in spans if s["name"] == "Kiro IDE turn"]
        self.assertEqual(len({t["spanId"] for t in turns}), 1)
        turn = turns[-1]
        self.assertEqual(turn["parentSpanId"], root_id)
        children = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn["spanId"])
        self.assertEqual(children, ["File saved", "Spec task", "execute_bash", "read_file"])
        self.assertGreaterEqual(int(root["endTimeUnixNano"]), int(turn["endTimeUnixNano"]))

    def test_tools_come_from_post_tool_use_and_mark_failures(self):
        spans = self.spans()
        read, = by_name(spans, "read_file")
        bash, = by_name(spans, "execute_bash")
        self.assertEqual(attrs(read)["gen_ai.tool.name"], "read_file")
        self.assertNotIn("gen_ai.tool.call.id", attrs(read))
        # Observe-only PostToolUse has no vendor duration; start and end are the hook time.
        self.assertEqual(int(read["endTimeUnixNano"]) - int(read["startTimeUnixNano"]), 0)
        self.assertEqual(read["status"]["code"], 1)
        self.assertEqual(bash["status"], {"code": 2, "message": "tool reported failure"})
        self.assertNotIn("coding_agent.incomplete", attrs(read))

    def test_spec_task_is_a_completed_span(self):
        task, = by_name(self.spans(), "Spec task")
        self.assertEqual(attrs(task)["kiro.task.success"], True)
        self.assertEqual(int(task["endTimeUnixNano"]) - int(task["startTimeUnixNano"]), 0)

    def test_retried_spec_task_keeps_the_failed_attempt(self):
        task = {"session_id": SID, "spec_name": "auth", "task_name": "1. Add login form"}
        records = self.records[:2] + [
            {"event": "PostTaskExec", "payload": {**task, "task_success": False}},
            {"event": "PostTaskExec", "payload": {**task, "task_success": True}},
        ]
        tasks = by_name(replay(kiro_ide, config("kiro_ide", self.tmp.name), records), "Spec task")
        self.assertEqual(len({t["spanId"] for t in tasks}), 2)
        self.assertEqual(sorted(t["status"]["code"] for t in tasks), [1, 2])
        self.assertEqual([t["status"].get("message") for t in tasks if t["status"]["code"] == 2],
                         ["spec task failed"])

    def test_default_export_has_no_content_or_paths(self):
        encoded = json.dumps(self.spans())
        for marker in MARKERS + DEFAULT_ONLY:
            self.assertNotIn(marker, encoded, marker)

    def test_opt_in_exports_content(self):
        spans = self.spans(capture=True)
        encoded = json.dumps(spans)
        for marker in MARKERS:
            self.assertIn(marker, encoded, marker)
        turn = [s for s in spans if s["name"] == "Kiro IDE turn"][-1]
        self.assertIn("PROMPT_MARKER_KIRO_IDE", attrs(turn)["input.value"])

    def test_cli_only_triggers_are_ignored(self):
        payload = {"session_id": "s", "hook_event_name": "agentSpawn", "cwd": "/x"}
        for event in ("agentSpawn", "AgentSpawn", "Manual", "userPromptSubmit"):
            self.assertEqual(kiro_ide.parse(event, payload), [])

    def test_missing_session_id_drops_event(self):
        payload = dict(self.records[2]["payload"])
        del payload["session_id"]
        self.assertEqual(kiro_ide.parse("PostToolUse", payload), [])

    def test_free_text_reason_is_not_exported(self):
        events = kiro_ide.parse("SessionEnd", {"session_id": "s", "reason": "the user closed it because..."})
        self.assertEqual([e.scope for e in events], ["turn", "session"])
        for ev in events:
            self.assertNotIn("kiro.session.end_reason", ev.attributes)
        ev = kiro_ide.parse("SessionEnd", {"session_id": "s", "reason": "other"})[-1]
        self.assertEqual(ev.attributes, {"kiro.session.end_reason": "other"})

    def test_pre_gating_hooks_are_not_mapped(self):
        payload = {"session_id": "s", "tool_name": "read_file", "tool_input": {"path": "/tmp/a"}}
        self.assertEqual(kiro_ide.parse("PreToolUse", payload), [])
        self.assertEqual(kiro_ide.parse("PreTaskExec", payload), [])

    def test_session_end_keeps_state_so_a_reloaded_session_continues(self):
        cfg = config("kiro_ide", self.tmp.name)
        first = replay(kiro_ide, cfg, self.records)  # ends with SessionEnd (runtime unload)
        root_id = emit.span_id("kiro_ide", SID, SESSION, "")
        first_root = latest(first, root_id)
        # Kiro reloads the same session id later; the chat continues.
        resumed = replay(kiro_ide, cfg, [
            {"event": "UserPromptSubmit", "payload": {"session_id": SID, "prompt": "second"}},
            {"event": "PostToolUse", "payload": {"session_id": SID, "tool_name": "read_file",
                                                 "tool_response": {"success": True}}},
            {"event": "Stop", "payload": {"session_id": SID}},
        ])
        turn_ids = {s["spanId"] for s in first + resumed if s["name"] == "Kiro IDE turn"}
        self.assertEqual(turn_ids, {emit.span_id("kiro_ide", SID, "turn", "turn-1"),
                                    emit.span_id("kiro_ide", SID, "turn", "turn-2")})
        root = latest(resumed, root_id)
        # Same root (id and start), now covering both visits.
        self.assertEqual(root["startTimeUnixNano"], first_root["startTimeUnixNano"])
        self.assertEqual(attrs(root)["kiro.session.end_reason"], "other")

    def test_session_end_closes_a_turn_that_is_still_open(self):
        records = self.records[:3] + [{"event": "SessionEnd", "payload": {"session_id": SID, "reason": "other"}}]
        spans = replay(kiro_ide, config("kiro_ide", self.tmp.name), records)
        turn = [s for s in spans if s["name"] == "Kiro IDE turn"][-1]
        self.assertEqual(attrs(turn)["kiro.turn.ended_by"], "SessionEnd")
        tool, = by_name(spans, "read_file")
        self.assertEqual(tool["parentSpanId"], turn["spanId"])
        # A late Stop after the unload does not re-open or duplicate the turn.
        late = replay(kiro_ide, config("kiro_ide", self.tmp.name), [{"event": "Stop", "payload": {"session_id": SID}}])
        self.assertEqual([s for s in late if s["name"] == "Kiro IDE turn"], [])

    def test_error_text_with_paths_is_not_exported_by_default(self):
        failure = {"success": False, "result": ["open /Users/alice.smith/secret/app.py: permission denied"]}
        records = self.records[:2] + [{"event": "PostToolUse", "payload": {
            "session_id": SID, "tool_name": "execute_bash", "tool_input": {"command": "cat /Users/alice.smith/x"},
            "tool_response": failure}}]
        encoded = json.dumps(replay(kiro_ide, config("kiro_ide", self.tmp.name), records))
        self.assertNotIn("alice.smith", encoded)
        self.assertNotIn("/Users/", encoded)
        self.assertIn("tool reported failure", encoded)

    def test_shipped_commands_fail_open_when_emitter_is_missing(self):
        root = pathlib.Path(__file__).resolve().parents[2] / "kiro-ide"
        for path in (root / "fi-hook-to-otlp.json", root / "fi-hook-to-otlp.user.json"):
            doc = json.loads(path.read_text())
            for hook in doc["hooks"]:
                command = hook["action"]["command"]
                result = subprocess.run(["sh", "-c", command], input="{}", text=True,
                                        capture_output=True, cwd=tempfile.mkdtemp())
                self.assertEqual(result.returncode, 0, (path, command, result.stderr))
                self.assertEqual(result.stdout, "", (path, command, result.stdout))

    def test_stdout_adds_nothing_to_agent_context(self):
        for event in ("SessionStart", "UserPromptSubmit", "PostTaskExec", "Stop"):
            self.assertEqual(kiro_ide.respond(event, {}), "")


if __name__ == "__main__":
    unittest.main()
