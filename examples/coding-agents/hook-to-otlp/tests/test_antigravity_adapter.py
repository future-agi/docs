"""Antigravity adapter contract tests.

session.jsonl is shaped as https://antigravity.google/docs/hooks?tab=ide
documents the payloads, plus the extra content fields of the Antigravity IDE
2.5.5 hook schema. real-cli-1.1.8*.jsonl were captured from a live Antigravity
CLI 1.1.8 (``agy -p``) run on 2026-10-18 and sanitized (fixture ids, paths and
markers only).
"""
from __future__ import annotations

import builtins
import io
import json
import tempfile
import unittest

from tests.helpers import FIXTURES, attrs, by_name, config, latest, load_jsonl, replay

import emit
from adapters import antigravity
from adapters.base import SESSION

SESSION_FIXTURE = FIXTURES / "antigravity" / "session.jsonl"
CONV = "fixture-ag-conv-0001"
MARKERS = ("PROMPT_MARKER_ANTIGRAVITY", "MODEL_OUTPUT_MARKER_ANTIGRAVITY", "TOOL_INPUT_MARKER_ANTIGRAVITY",
           "TOOL_OUTPUT_MARKER_ANTIGRAVITY", "ERROR_MARKER_ANTIGRAVITY", "RESPONSE_MARKER_ANTIGRAVITY")
# Never exported, even with content capture on.
NEVER = ("transcript-CANARY", "/.gemini/antigravity-ide/brain")
# Workspace paths only appear inside opted-in tool arguments.
DEFAULT_ONLY = ("/Users/fixture/project",)


class AntigravityAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = load_jsonl(SESSION_FIXTURE)
        for record in self.records:  # the hook command passes the event on argv
            record["argv_event"] = record["event"]

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, capture=False):
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(antigravity, config("antigravity", self.tmp.name, **extra), self.records)

    def test_one_trace_session_turn_model_and_tools(self):
        spans = self.spans()
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("antigravity", CONV)})
        root_id = emit.span_id("antigravity", CONV, SESSION, "")
        root = latest(spans, root_id)
        self.assertEqual(root["name"], "Antigravity session")
        self.assertEqual(attrs(root)["llm.model_name"], "gemini-3.6-flash-medium")
        turns = [s for s in spans if s["name"] == "Antigravity turn"]
        self.assertEqual(len({t["spanId"] for t in turns}), 1)
        turn = turns[-1]
        self.assertEqual(turn["parentSpanId"], root_id)
        self.assertEqual(attrs(turn)["antigravity.stop.termination_reason"], "model_stop")
        children = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn["spanId"])
        self.assertEqual(children, ["Model call", "Model call", "Model call", "list_dir", "run_command"])

    def test_tools_come_from_post_tool_use_and_mark_errors(self):
        spans = self.spans()
        ok, = by_name(spans, "list_dir")
        failed, = by_name(spans, "run_command")
        a = attrs(ok)
        self.assertEqual((a["fi.span.kind"], a["gen_ai.tool.name"], a["gen_ai.tool.call.id"]),
                         ("TOOL", "list_dir", "step-2"))
        self.assertEqual(ok["status"]["code"], 1)
        self.assertEqual(failed["status"], {"code": 2, "message": "tool error"})
        # PostToolUse-only observation has no vendor duration.
        self.assertEqual(int(ok["endTimeUnixNano"]) - int(ok["startTimeUnixNano"]), 0)

    def test_model_calls_pair_and_carry_model(self):
        calls = by_name(self.spans(), "Model call")
        self.assertEqual(len({c["spanId"] for c in calls}), 3)
        for call in calls:
            self.assertEqual(attrs(call)["fi.span.kind"], "LLM")
            self.assertEqual(attrs(call)["gen_ai.request.model"], "gemini-3.6-flash-medium")

    def test_default_export_has_no_content_or_paths(self):
        encoded = json.dumps(self.spans())
        for marker in MARKERS + NEVER + DEFAULT_ONLY:
            self.assertNotIn(marker, encoded, marker)

    def test_opt_in_exports_content_but_never_transcript(self):
        spans = self.spans(capture=True)
        encoded = json.dumps(spans)
        for marker in MARKERS:
            self.assertIn(marker, encoded, marker)
        for marker in NEVER:
            self.assertNotIn(marker, encoded, marker)
        failed, = by_name(spans, "run_command")
        self.assertIn("ERROR_MARKER_ANTIGRAVITY", failed["status"]["message"])

    def test_transcript_and_artifacts_are_never_opened(self):
        opened = []
        real_open, real_io_open = builtins.open, io.open

        def spy(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        builtins.open = io.open = spy
        try:
            self.spans(capture=True)
        finally:
            builtins.open, io.open = real_open, real_io_open
        self.assertFalse([p for p in opened if "transcript" in p or "/brain/" in p], opened)

    def test_event_name_comes_from_argv_only(self):
        payload = self.records[3]["payload"]
        self.assertEqual(antigravity.event_name("PostToolUse", payload), "PostToolUse")
        self.assertIsNone(antigravity.event_name(None, payload))
        self.assertEqual(antigravity.parse("", payload), [])

    def test_missing_conversation_id_drops_event(self):
        payload = dict(self.records[3]["payload"])
        del payload["conversationId"]
        self.assertEqual(antigravity.parse("PostToolUse", payload), [])

    def test_pre_tool_use_is_not_mapped(self):
        payload = {**self.records[4]["payload"], "toolCall": {"name": "run_command", "args": {}}}
        self.assertEqual(antigravity.parse("PreToolUse", payload), [])

    def test_zero_valued_fields_left_out_by_protojson_still_open_the_turn(self):
        records = []
        for record in self.records:
            payload = {k: v for k, v in record["payload"].items() if v not in (0, "", False)}
            records.append({**record, "payload": payload})
        spans = replay(antigravity, config("antigravity", self.tmp.name), records)
        turn = [s for s in spans if s["name"] == "Antigravity turn"][-1]
        children = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn["spanId"])
        self.assertEqual(children, ["Model call", "Model call", "Model call", "list_dir", "run_command"])
        self.assertEqual(len({s["spanId"] for s in by_name(spans, "Model call")}), 3)

    def test_error_text_with_paths_is_not_exported_by_default(self):
        records = self.records[:3] + [{"argv_event": "PostToolUse", "event": "PostToolUse", "payload": {
            **self.records[3]["payload"], "error": "open /Users/alice.smith/secret/app.py: permission denied"}}]
        encoded = json.dumps(replay(antigravity, config("antigravity", self.tmp.name), records))
        self.assertNotIn("alice.smith", encoded)
        self.assertIn("tool error", encoded)

    def test_stdout_contract_never_blocks(self):
        self.assertNotEqual(json.loads(antigravity.respond("Stop", {}))["decision"], "continue")
        for event in ("SessionStart", "PreInvocation", "PostInvocation", "PostToolUse"):
            self.assertEqual(json.loads(antigravity.respond(event, {})), {})

    def test_app_sessions_are_dropped_ide_and_cli_are_labelled(self):
        payload = dict(self.records[3]["payload"])
        base = f"/Users/fixture/.gemini/antigravity/brain/{CONV}"
        app = {**payload, "artifactDirectoryPath": base, "transcriptPath": base + "/transcript.jsonl"}
        self.assertEqual(antigravity.parse("PostToolUse", app), [])
        windows = f"C:\\Users\\x\\.gemini\\antigravity\\brain\\{CONV}"
        self.assertEqual(antigravity.parse("PostToolUse", {**payload, "artifactDirectoryPath": windows}), [])
        for app_dir, label in (("antigravity-ide", "ide"), ("antigravity-cli", "cli")):
            for path in (f"/Users/fixture/.gemini/{app_dir}/brain/{CONV}",
                         f"C:\\Users\\x\\.gemini\\{app_dir}\\brain\\{CONV}"):
                other = {**payload, "artifactDirectoryPath": path, "transcriptPath": path + "/transcript.jsonl"}
                self.assertTrue(antigravity.parse("PostToolUse", other), path)
                self.assertEqual(antigravity.surface(other), label, path)
                start, = antigravity.parse("SessionStart", other)
                self.assertEqual(start.attributes, {"antigravity.surface": label})
        # Neither path: traced, without a surface label.
        bare = {k: v for k, v in payload.items() if k not in ("artifactDirectoryPath", "transcriptPath")}
        self.assertTrue(antigravity.parse("PostToolUse", bare))
        self.assertEqual(antigravity.parse("SessionStart", bare)[0].attributes, {})

    def test_upper_case_error_termination_reason_marks_the_turn(self):
        stop = {**self.records[-1]["payload"], "terminationReason": "ERROR", "error": ""}
        records = self.records[:-1] + [{"argv_event": "Stop", "event": "Stop", "payload": stop}]
        spans = replay(antigravity, config("antigravity", self.tmp.name), records)
        turn = [s for s in spans if s["name"] == "Antigravity turn"][-1]
        self.assertEqual(turn["status"], {"code": 2, "message": "execution ended with error"})
        self.assertEqual(attrs(turn)["antigravity.stop.termination_reason"], "ERROR")

    def test_gemini_cli_style_payload_is_not_mapped(self):
        # Gemini CLI hooks use snake_case session_id and their own event names.
        gemini = {"session_id": "g1", "hook_event_name": "BeforeTool", "tool_name": "read_file"}
        self.assertEqual(antigravity.parse("BeforeTool", gemini), [])
        self.assertEqual(antigravity.parse("PreToolUse", gemini), [])


REAL = FIXTURES / "antigravity" / "real-cli-1.1.8.jsonl"
REAL_ERRORS = FIXTURES / "antigravity" / "real-cli-1.1.8-tool-error.jsonl"
REAL_CONV, REAL_ERROR_CONV = "fixture-agy-conv-0001", "fixture-agy-conv-0002"
# Present in the captured payloads; never exported by default.
REAL_DEFAULT_ABSENT = ("/Users/fixture", "/.gemini/", "brain", "transcript", "AGY_TOOL_INPUT_MARKER", "README.md",
                       "toolSummary", "permission denied", "target content not found")


class AntigravityRealCliTest(unittest.TestCase):
    """Payloads from a live Antigravity CLI 1.1.8 run (sanitized)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, fixture, capture=False):
        records = load_jsonl(fixture)
        for record in records:
            record["argv_event"] = record["event"]
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(antigravity, config("antigravity", self.tmp.name, **extra), records)

    def children(self, spans, parent):
        return sorted(s["name"] for s in {s["spanId"]: s for s in spans if s.get("parentSpanId") == parent}.values())

    def test_session_with_a_resumed_second_turn_is_one_trace(self):
        spans = self.spans(REAL)
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("antigravity", REAL_CONV)})
        root_id = emit.span_id("antigravity", REAL_CONV, SESSION, "")
        root = latest(spans, root_id)
        self.assertEqual((root["name"], attrs(root)["antigravity.surface"], attrs(root)["llm.model_name"]),
                         ("Antigravity session", "cli", "gemini-4-argon-medium"))
        turns = {s["spanId"]: s for s in spans if s["name"] == "Antigravity turn"}
        self.assertEqual(len(turns), 2, "the resumed conversation (no SessionStart, invocationNum 0) opens turn 2")
        first, second = sorted(turns.values(), key=lambda t: int(t["startTimeUnixNano"]))
        for turn in (first, second):
            a = attrs(turn)
            self.assertEqual(turn["parentSpanId"], root_id)
            self.assertEqual(turn["status"]["code"], 1)
            self.assertEqual((a["antigravity.surface"], a["antigravity.stop.termination_reason"],
                              a["antigravity.stop.execution_num"], a["antigravity.stop.fully_idle"]),
                             ("cli", "NO_TOOL_CALL", "0", True))  # OTLP intValue is a string
        self.assertEqual(self.children(spans, first["spanId"]),
                         ["Model call", "Model call", "Model call", "run_command", "run_command", "view_file"])
        self.assertEqual(self.children(spans, second["spanId"]), ["Model call", "Model call", "view_file"])
        call_ids = sorted(attrs(s)["gen_ai.tool.call.id"] for s in spans if attrs(s).get("fi.span.kind") == "TOOL")
        self.assertEqual(sorted(set(call_ids)), ["step-10", "step-2", "step-3", "step-5"])

    def test_model_call_spans_cover_their_tool_calls(self):
        # CLI 1.1.8 sends PostToolUse before the PostInvocation of the same response.
        spans = self.spans(REAL)
        first_call = min({s["spanId"]: s for s in by_name(spans, "Model call")}.values(),
                         key=lambda s: int(s["startTimeUnixNano"]))
        tool = min(by_name(spans, "run_command"), key=lambda s: int(s["startTimeUnixNano"]))
        self.assertLessEqual(int(first_call["startTimeUnixNano"]), int(tool["startTimeUnixNano"]))
        self.assertGreaterEqual(int(first_call["endTimeUnixNano"]), int(tool["endTimeUnixNano"]))

    def test_tool_errors_are_marked_and_their_text_is_content(self):
        spans = self.spans(REAL_ERRORS)
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("antigravity", REAL_ERROR_CONV)})
        for name in ("replace_file_content", "write_to_file"):
            span, = by_name(spans, name)
            self.assertEqual(span["status"], {"code": 2, "message": "tool error"}, name)
        turn = [s for s in spans if s["name"] == "Antigravity turn"][-1]
        self.assertEqual(turn["status"]["code"], 1, "the execution itself ended normally (NO_TOOL_CALL)")
        opted = self.spans(REAL_ERRORS, capture=True)
        self.assertIn("target content not found", by_name(opted, "replace_file_content")[0]["status"]["message"])
        self.assertIn("permission denied", by_name(opted, "write_to_file")[0]["status"]["message"])

    def test_default_export_has_no_paths_or_content(self):
        for fixture in (REAL, REAL_ERRORS):
            encoded = json.dumps(self.spans(fixture))
            for marker in REAL_DEFAULT_ABSENT:
                self.assertNotIn(marker, encoded, f"{fixture.name}: {marker}")

    def test_opt_in_adds_tool_arguments_but_never_transcript_or_account_name(self):
        encoded = json.dumps(self.spans(REAL, capture=True))
        self.assertIn("AGY_TOOL_INPUT_MARKER", encoded)
        self.assertIn("README.md", encoded)
        for marker in ("transcript", "/brain/", "/Users/fixture"):
            self.assertNotIn(marker, encoded, marker)


if __name__ == "__main__":
    unittest.main()
