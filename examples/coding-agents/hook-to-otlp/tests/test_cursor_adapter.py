"""Cursor adapter contract tests against payloads shaped as https://cursor.com/docs/hooks documents them."""
from __future__ import annotations

import builtins
import io
import json
import tempfile
import unittest

from tests.helpers import FIXTURES, attrs, by_name, config, latest, load_jsonl, replay

import emit
from adapters import cursor
from adapters.base import SESSION, TURN

SESSION_FIXTURE = FIXTURES / "cursor" / "session.jsonl"
MARKERS = ("PROMPT_MARKER_CURSOR", "THOUGHT_MARKER_CURSOR", "TOOL_INPUT_MARKER_CURSOR",
           "TOOL_OUTPUT_MARKER_CURSOR", "ERROR_MARKER_CURSOR", "SUBAGENT_MARKER_CURSOR",
           "RESPONSE_MARKER_CURSOR")
# Never exported, even with content capture on.
NEVER = ("fixture.user@example.com", "fixture-transcript-CANARY", "fixture-subagent-transcript")
# Paths only appear inside opted-in content (tool input), never as metadata.
DEFAULT_ONLY = ("/Users/fixture/project",)


class CursorAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = load_jsonl(SESSION_FIXTURE)

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, capture=False):
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(cursor, config("cursor", self.tmp.name, **extra), self.records)

    def test_one_trace_with_session_turn_tool_tree(self):
        spans = self.spans()
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("cursor", "fixture-conv-0001")})
        root_id = emit.span_id("cursor", "fixture-conv-0001", SESSION, "")
        turn_id = emit.span_id("cursor", "fixture-conv-0001", TURN, "fixture-gen-0001")
        root = latest(spans, root_id)
        self.assertEqual(root["name"], "Cursor session")
        self.assertEqual(attrs(root)["fi.span.kind"], "AGENT")
        turn = latest(spans, turn_id)
        self.assertEqual(turn["name"], "Cursor turn")
        self.assertEqual(turn["parentSpanId"], root_id)
        self.assertEqual(attrs(turn)["llm.model_name"], "claude-opus-4-7")
        self.assertEqual(attrs(turn)["cursor.model"], "claude-opus-4-7-thinking-max")
        self.assertEqual(attrs(turn)["cursor.model_params.effort"], "max")
        names = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn_id)
        self.assertEqual(names, ["Agent response", "Agent thought", "Context compaction",
                                 "Read", "Shell", "Shell", "Subagent: explore"])
        # Session end ran last; the root is final and ended after the turn.
        self.assertGreaterEqual(int(root["endTimeUnixNano"]), int(turn["endTimeUnixNano"]))
        self.assertEqual(attrs(root)["cursor.session.reason"], "user_close")

    def test_tools_use_vendor_duration_and_ids(self):
        shell_ok, shell_failed = by_name(self.spans(), "Shell")
        self.assertEqual(int(shell_ok["endTimeUnixNano"]) - int(shell_ok["startTimeUnixNano"]), 420_000_000)
        a = attrs(shell_ok)
        self.assertEqual((a["fi.span.kind"], a["gen_ai.tool.name"], a["gen_ai.tool.call.id"]),
                         ("TOOL", "Shell", "toolu_fixture_1"))
        self.assertEqual(shell_ok["status"]["code"], 1)
        self.assertEqual(shell_failed["status"], {"code": 2, "message": "timeout"})
        self.assertEqual(attrs(shell_failed)["cursor.tool.failure_type"], "timeout")

    def test_subagent_and_compaction_metadata(self):
        spans = self.spans()
        sub = by_name(spans, "Subagent: explore")[0]
        self.assertEqual(attrs(sub)["cursor.subagent.tool_call_count"], "3")
        self.assertEqual(int(sub["endTimeUnixNano"]) - int(sub["startTimeUnixNano"]), 4_000_000_000)
        compaction = attrs(by_name(spans, "Context compaction")[0])
        self.assertEqual(compaction["cursor.compaction.context_tokens"], "120000")

    def test_default_export_has_no_content_or_pii(self):
        encoded = json.dumps(self.spans())
        for marker in MARKERS + NEVER + DEFAULT_ONLY:
            self.assertNotIn(marker, encoded, marker)

    def test_opt_in_exports_content_but_never_pii(self):
        spans = self.spans(capture=True)
        encoded = json.dumps(spans)
        for marker in MARKERS:
            self.assertIn(marker, encoded, marker)
        for marker in NEVER:
            self.assertNotIn(marker, encoded, marker)
        turn = latest(spans, emit.span_id("cursor", "fixture-conv-0001", TURN, "fixture-gen-0001"))
        self.assertIn("PROMPT_MARKER_CURSOR", attrs(turn)["input.value"])
        self.assertIn("RESPONSE_MARKER_CURSOR", attrs(turn)["output.value"])
        failed = by_name(spans, "Shell")[1]
        self.assertIn("ERROR_MARKER_CURSOR", failed["status"]["message"])

    def test_transcript_path_is_never_opened(self):
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
        self.assertFalse([p for p in opened if "transcript" in p], opened)

    def test_missing_conversation_id_drops_event(self):
        payload = dict(self.records[3]["payload"])
        del payload["conversation_id"]
        self.assertEqual(cursor.parse("postToolUse", payload), [])

    def test_real_cursor_3_24_18_session_end_payload(self):
        # Captured from the Cursor 3.24.18 Hooks output channel (empty chat closed with the window).
        record = load_jsonl(FIXTURES / "cursor" / "real-3.24.18.jsonl")[0]
        events = cursor.parse(record["event"], record["payload"])
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].phase, events[0].scope), ("end", SESSION))
        self.assertEqual(events[0].attributes["cursor.session.reason"], "window_close")
        # An empty conversation is not exported.
        self.assertEqual(replay(cursor, config("cursor", self.tmp.name), [record]), [])

    def test_real_cursor_3_24_18_agent_turn(self):
        # One real IDE agent turn on the Hobby plan (beforeSubmitPrompt, thoughts, Read, Grep, response, stop).
        records = load_jsonl(FIXTURES / "cursor" / "real-3.24.18-turn.jsonl")
        spans = replay(cursor, config("cursor", self.tmp.name), records)
        sid = records[0]["payload"]["conversation_id"]
        gen = records[0]["payload"]["generation_id"]
        self.assertEqual({s["traceId"] for s in spans}, {emit.trace_id("cursor", sid)})
        turn_id = emit.span_id("cursor", sid, TURN, gen)
        turns = {s["spanId"] for s in spans if attrs(s)["coding_agent.scope"] == "turn"}
        self.assertEqual(turns, {turn_id}, "suffixed generation ids must not open extra turns")
        children = {}
        for span in spans:
            if span.get("parentSpanId") == turn_id:
                children[span["spanId"]] = span["name"]
        self.assertEqual(sorted(children.values()), ["Agent response", "Agent thought", "Agent thought", "Grep", "Read"])
        response = latest(spans, [k for k, v in children.items() if v == "Agent response"][0])
        a = attrs(response)
        self.assertEqual((a["llm.token_count.prompt"], a["llm.token_count.completion"], a["llm.token_count.total"]),
                         ("38779", "306", "39085"))
        self.assertEqual(a["llm.token_count.prompt_details.cache_read"], "24192")
        self.assertEqual(a["llm.model_name"], "grok-4.6")
        read = [s for s in spans if s["name"] == "Read"][0]
        self.assertEqual(attrs(read)["gen_ai.tool.call.id"], "call-f3e41504-16cd-4345-9614-dccb061cbdd4-1")
        self.assertEqual(attrs(read)["cursor.tool.provider_call_id"], "fc_cdbfcc58-3e58-9ca2-92f0-366509226caf_1")
        self.assertFalse(any("\n" in str(v) for s in spans for v in attrs(s).values()))
        turn = latest(spans, turn_id)
        self.assertEqual(attrs(turn)["cursor.usage.input_tokens"], "38779")
        self.assertNotIn("llm.token_count.prompt", attrs(turn))
        encoded = json.dumps(spans)
        for marker in ("PROMPT_MARKER_REAL", "THOUGHT_MARKER_REAL", "RESPONSE_MARKER_REAL",
                       "TOOL_OUTPUT_MARKER_REAL") + NEVER + DEFAULT_ONLY:
            self.assertNotIn(marker, encoded, marker)

    def test_stdout_contract(self):
        self.assertEqual(json.loads(cursor.respond("beforeSubmitPrompt", {})), {"continue": True})
        self.assertEqual(json.loads(cursor.respond("stop", {})), {})
        self.assertEqual(json.loads(cursor.respond("sessionStart", {})), {})
        self.assertEqual(json.loads(cursor.respond("preToolUse", {})), {"permission": "allow"})

    def test_unmapped_hooks_are_ignored(self):
        for hook in ("afterShellExecution", "afterFileEdit", "beforeTabFileRead", "workspaceOpen"):
            self.assertEqual(cursor.parse(hook, {"conversation_id": "c", "generation_id": "g"}), [])

    def test_resource_carries_cursor_version(self):
        cfg = config("cursor", self.tmp.name)
        body = emit.build_body(cursor, cfg, "stop", self.records[0]["payload"], [])
        resource = attrs(body["resourceSpans"][0]["resource"])
        self.assertEqual(resource["coding_agent.app.version"], "3.24.18")
        self.assertNotIn("fixture.user@example.com", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
