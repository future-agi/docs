"""Kiro CLI adapter contract tests.

Payloads follow https://kiro.dev/docs/hooks/types/ (CLI V3) and the hook
fields named in the kiro-cli-chat 2.31.1 binary.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
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
        self.assertEqual(children, ["glob", "read_file"])

    def test_tools_pair_and_failures_are_errors(self):
        spans = self.spans()
        glob, = by_name(spans, "glob")
        read, = by_name(spans, "read_file")
        self.assertEqual(int(glob["endTimeUnixNano"]) - int(glob["startTimeUnixNano"]), 1_000_000_000)
        self.assertEqual(glob["status"]["code"], 1)
        self.assertEqual(read["status"], {"code": 2, "message": "tool reported failure"})

    def test_agent_spawn_and_cli2_names_are_accepted(self):
        renamed = {"SessionStart": "agentSpawn", "UserPromptSubmit": "userPromptSubmit",
                   "PreToolUse": "preToolUse", "PostToolUse": "postToolUse", "Stop": "stop"}
        records = []
        for record in self.records:
            event = renamed.get(record["event"], record["event"])
            records.append({"event": event, "payload": {**record["payload"], "hook_event_name": event}})
        spans = self.spans(records=records)
        self.assertEqual(sorted({s["name"] for s in spans}),
                         ["Kiro CLI session", "Kiro CLI turn", "glob", "read_file"])
        root = latest(spans, emit.span_id("kiro_cli", SID, SESSION, ""))
        self.assertEqual(attrs(root)["kiro.hook.trigger"], "agentSpawn")

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
        self.assertEqual(kiro_cli.parse("PreToolUse", payload), [])

    def test_shipped_commands_fail_open_when_emitter_is_missing(self):
        root = pathlib.Path(__file__).resolve().parents[2] / "kiro-cli"
        for path in (root / "fi-hook-to-otlp.json", root / "fi-hook-to-otlp.user.json"):
            doc = json.loads(path.read_text())
            for hook in doc["hooks"]:
                command = hook["action"]["command"]
                result = subprocess.run(["sh", "-c", command], input="{}", text=True,
                                        capture_output=True, cwd=tempfile.mkdtemp())
                self.assertEqual(result.returncode, 0, (path, command, result.stderr))
                self.assertEqual(result.stdout, "", (path, command, result.stdout))

    def test_stdout_adds_nothing_to_agent_context(self):
        for event in ("SessionStart", "UserPromptSubmit", "Stop"):
            self.assertEqual(kiro_cli.respond(event, {}), "")


if __name__ == "__main__":
    unittest.main()
