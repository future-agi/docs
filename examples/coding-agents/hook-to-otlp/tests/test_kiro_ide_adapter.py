"""Kiro IDE adapter contract tests.

Payloads follow https://kiro.dev/docs/hooks/types/ and the payload builder in
the Kiro IDE 1.2.37 ``kiro.kiro-agent`` extension.
"""
from __future__ import annotations

import json
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
        self.assertEqual(attrs(root)["kiro.session.end_reason"], "other")
        turns = [s for s in spans if s["name"] == "Kiro IDE turn"]
        self.assertEqual(len({t["spanId"] for t in turns}), 1)
        turn = turns[-1]
        self.assertEqual(turn["parentSpanId"], root_id)
        children = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn["spanId"])
        self.assertEqual(children, ["File saved", "Spec task", "execute_bash", "read_file"])
        self.assertGreaterEqual(int(root["endTimeUnixNano"]), int(turn["endTimeUnixNano"]))

    def test_tools_pair_pre_and_post_and_mark_failures(self):
        spans = self.spans()
        read, = by_name(spans, "read_file")
        bash, = by_name(spans, "execute_bash")
        self.assertEqual(attrs(read)["gen_ai.tool.name"], "read_file")
        self.assertEqual(int(read["endTimeUnixNano"]) - int(read["startTimeUnixNano"]), 1_000_000_000)
        self.assertEqual(read["status"]["code"], 1)
        self.assertEqual(bash["status"], {"code": 2, "message": "tool reported failure"})
        self.assertNotIn("coding_agent.incomplete", attrs(read))

    def test_spec_task_pairs_on_names(self):
        task, = by_name(self.spans(), "Spec task")
        self.assertEqual(attrs(task)["kiro.task.success"], True)
        self.assertEqual(int(task["endTimeUnixNano"]) - int(task["startTimeUnixNano"]), 1_000_000_000)

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
        self.assertEqual(kiro_ide.parse("PreToolUse", payload), [])

    def test_free_text_reason_is_not_exported(self):
        ev, = kiro_ide.parse("SessionEnd", {"session_id": "s", "reason": "the user closed it because..."})
        self.assertNotIn("kiro.session.end_reason", ev.attributes)

    def test_stdout_adds_nothing_to_agent_context(self):
        for event in ("SessionStart", "UserPromptSubmit", "PreTaskExec", "Stop"):
            self.assertEqual(kiro_ide.respond(event, {}), "")


if __name__ == "__main__":
    unittest.main()
