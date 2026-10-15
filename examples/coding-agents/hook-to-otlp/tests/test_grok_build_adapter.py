"""Grok Build adapter contract tests.

``session.jsonl`` is a sanitized capture from a real grok 1.0.52 session
(ids, paths and bodies replaced, keys kept). ``edge.jsonl`` is shaped as
https://docs.x.ai/build/features/hooks and the bundled hooks guide document
the failure, denial, compaction and cancel events, plus shell results with
a non-zero exit, a timeout, and a truncated (string) result, using the
``toolResult`` keys of a real grok 1.0.52 ``run_terminal_command``.
"""
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
from adapters import grok_build
from adapters.base import OK, SESSION, SUBAGENT, TOOL, TURN

SESSION_FIXTURE = FIXTURES / "grok_build" / "session.jsonl"
EDGE_FIXTURE = FIXTURES / "grok_build" / "edge.jsonl"
PARENT = "fixture-grok-session-0001"
CHILD = "fixture-grok-session-0002"
MARKERS = ("PROMPT_MARKER_GROK", "TOOL_INPUT_MARKER_GROK", "TOOL_OUTPUT_MARKER_GROK",
           "RESPONSE_MARKER_GROK", "SUBAGENT_TASK_MARKER_GROK", "ERROR_MARKER_GROK")
# Never exported, even with content capture on.
NEVER = ("fixture-transcript-CANARY", "NOTIFICATION_MARKER_GROK")
# Paths only appear inside opted-in content, never as metadata; the
# error-details path (with a user name) only with content capture on.
DEFAULT_ONLY = ("/Users/fixture/project", "/Users/alice")


def by_call_id(spans, call_id):
    return [s for s in spans if attrs(s).get("gen_ai.tool.call.id") == call_id]


class GrokBuildAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def spans(self, fixture=SESSION_FIXTURE, capture=False):
        extra = {"FI_HOOK_CAPTURE_CONTENT": "1"} if capture else {}
        return replay(grok_build, config("grok_build", self.tmp.name, **extra), load_jsonl(fixture))

    def test_event_name_from_payload(self):
        self.assertEqual(grok_build.event_name(None, {"hook_event_name": "PreToolUse"}), "PreToolUse")
        self.assertEqual(grok_build.event_name(None, {"hookEventName": "post_tool_use_failure"}), "PostToolUseFailure")
        self.assertEqual(grok_build.event_name("Stop", {"hook_event_name": "PreToolUse"}), "Stop")

    def test_parent_session_is_one_trace_with_turn_and_tools(self):
        spans = [s for s in self.spans() if s["traceId"] == emit.trace_id("grok_build", PARENT)]
        root_id = emit.span_id("grok_build", PARENT, SESSION, "")
        turn_id = emit.span_id("grok_build", PARENT, TURN, "fixture-grok-prompt-0001")
        root = latest(spans, root_id)
        self.assertEqual(root["name"], "Grok Build session")
        self.assertEqual(attrs(root)["fi.span.kind"], "AGENT")
        self.assertEqual(attrs(root)["grok_build.session.source"], "new")
        self.assertEqual(attrs(root)["grok_build.session.end_reason"], "shutdown")
        turn = latest(spans, turn_id)
        self.assertEqual(turn["parentSpanId"], root_id)
        self.assertEqual(turn["status"]["code"], 1)
        self.assertEqual(attrs(turn)["grok_build.stop.reason"], "end_turn")
        children = sorted(s["name"] for s in spans if s.get("parentSpanId") == turn_id)
        self.assertEqual(children, ["Subagent: general-purpose", "get_command_or_subagent_output",
                                    "read_file", "spawn_subagent"])
        read = by_name(spans, "read_file")[0]
        a = attrs(read)
        self.assertEqual((a["fi.span.kind"], a["gen_ai.tool.name"], a["gen_ai.tool.call.id"]),
                         ("TOOL", "read_file", "call_fixture-0002"))
        self.assertEqual(a["grok_build.tool.outcome"], "success")

    def test_session_end_stop_without_prompt_is_not_a_turn(self):
        turns = [s for s in self.spans() if attrs(s).get("coding_agent.scope") == TURN
                 and s["traceId"] == emit.trace_id("grok_build", PARENT)]
        self.assertEqual({s["spanId"] for s in turns},
                         {emit.span_id("grok_build", PARENT, TURN, "fixture-grok-prompt-0001")})

    def test_subagent_is_linked_not_reparented(self):
        spans = self.spans()
        sub = by_name(spans, "Subagent: general-purpose")[0]
        self.assertEqual(sub["traceId"], emit.trace_id("grok_build", PARENT))
        self.assertEqual(attrs(sub)["grok_build.subagent.id"], CHILD)
        self.assertEqual(attrs(sub)["fi.span.kind"], "AGENT")
        child = [s for s in spans if s["traceId"] == emit.trace_id("grok_build", CHILD)]
        child_roots = [s for s in child if s["spanId"] == emit.span_id("grok_build", CHILD, SESSION, "")]
        # Named as a subagent session in every export, not only the last one.
        self.assertEqual({s["name"] for s in child_roots}, {"Grok Build subagent session: general-purpose"})
        child_root = child_roots[-1]
        self.assertNotIn("parentSpanId", child_root)
        child_turn = latest(child, emit.span_id("grok_build", CHILD, TURN, "fixture-grok-prompt-0002"))
        self.assertEqual(attrs(child_turn)["grok_build.subagent.type"], "general-purpose")
        self.assertEqual([s["name"] for s in child if attrs(s).get("coding_agent.scope") == TOOL],
                         ["run_terminal_command"])

    def test_tool_duration_is_grok_duration_ms(self):
        wait = by_name(self.spans(), "get_command_or_subagent_output")[0]
        self.assertEqual(int(wait["endTimeUnixNano"]) - int(wait["startTimeUnixNano"]), 3_465_000_000)
        self.assertEqual(attrs(wait)["grok_build.tool.duration_ms"], 3465.0)

    def test_pre_tool_use_is_not_mapped(self):
        pre = [r for r in load_jsonl(SESSION_FIXTURE) if r["event"] == "PreToolUse"]
        self.assertTrue(pre)
        for record in pre:
            self.assertEqual(grok_build.parse("PreToolUse", record["payload"]), [])

    def test_failures_denials_and_cancels(self):
        spans = self.spans(EDGE_FIXTURE)
        failed = by_name(spans, "github__search_repositories")[0]
        self.assertEqual(failed["status"], {"code": 2, "message": "tool failed"})
        self.assertEqual(attrs(failed)["grok_build.tool.outcome"], "failure")
        denied = by_call_id(spans, "call_fixture_edge_2")[0]
        self.assertEqual(denied["status"], {"code": 2, "message": "permission denied"})
        turn1 = latest(spans, emit.span_id("grok_build", "fixture-grok-session-0101", TURN, "fixture-grok-prompt-0101"))
        self.assertEqual(turn1["status"], {"code": 2, "message": "rate_limit"})
        self.assertEqual(attrs(turn1)["grok_build.stop.event"], "StopFailure")
        turn2 = latest(spans, emit.span_id("grok_build", "fixture-grok-session-0101", TURN, "fixture-grok-prompt-0102"))
        self.assertEqual(turn2["status"], {"code": 0})
        self.assertEqual(attrs(turn2)["grok_build.stop.reason"], "user_interrupt")
        self.assertEqual(attrs(turn2)["grok_build.stop.cancelled_by"], "user")
        self.assertEqual(attrs(by_name(spans, "Context compaction")[0])["grok_build.compaction.trigger"], "auto")
        self.assertEqual(len({s["traceId"] for s in spans}), 1)

    def test_shell_exit_code_and_timeout(self):
        spans = self.spans(EDGE_FIXTURE)
        exit1 = by_call_id(spans, "call_fixture_edge_exit1")[0]
        self.assertEqual(exit1["status"], {"code": 2, "message": "exit code 1"})
        self.assertEqual(attrs(exit1)["grok_build.tool.exit_code"], "1")
        self.assertEqual(attrs(exit1)["grok_build.tool.outcome"], "failure")
        timeout = by_call_id(spans, "call_fixture_edge_timeout")[0]
        self.assertEqual(timeout["status"], {"code": 2, "message": "timed out"})
        self.assertIs(attrs(timeout)["grok_build.tool.timed_out"], True)
        self.assertEqual(attrs(timeout)["grok_build.tool.signal"], "SIGKILL")
        truncated = attrs(by_call_id(spans, "call_fixture_edge_truncated")[0])
        self.assertNotIn("grok_build.tool.exit_code", truncated)  # string result: not parsed
        self.assertEqual(truncated["grok_build.tool.outcome"], "success")
        # A real capture's shell call (exit 0) stays OK.
        ok = [s for s in self.spans() if s["name"] == "run_terminal_command"]
        self.assertTrue(ok)
        self.assertEqual({s["status"]["code"] for s in ok}, {1})

    def test_default_export_has_no_content_or_paths(self):
        encoded = json.dumps(self.spans() + self.spans(EDGE_FIXTURE))
        for marker in MARKERS + NEVER + DEFAULT_ONLY:
            self.assertNotIn(marker, encoded, marker)

    def test_capture_content_opt_in(self):
        spans = self.spans(capture=True)
        turn = latest(spans, emit.span_id("grok_build", PARENT, TURN, "fixture-grok-prompt-0001"))
        self.assertIn("PROMPT_MARKER_GROK", attrs(turn)["input.value"])
        self.assertIn("RESPONSE_MARKER_GROK", attrs(turn)["output.value"])
        read = attrs(by_name(spans, "read_file")[0])
        self.assertIn("TOOL_INPUT_MARKER_GROK", read["input.value"])
        self.assertIn("TOOL_OUTPUT_MARKER_GROK", read["output.value"])
        edge = json.dumps(self.spans(EDGE_FIXTURE, capture=True))
        self.assertIn("ERROR_MARKER_GROK_DETAILS", edge)
        # Opted-in error text keeps the path but not the user name in it.
        self.assertNotIn("/Users/alice", edge)
        self.assertIn("/Users/<user>/work/.grok/config.toml", edge)
        encoded = json.dumps(spans) + edge
        for marker in NEVER:
            self.assertNotIn(marker, encoded, marker)

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
            self.spans(EDGE_FIXTURE, capture=True)
        self.assertTrue(opened)  # the spies saw the state files
        self.assertFalse([p for p in opened if "CANARY" in p], opened)

    def test_free_text_never_becomes_metadata(self):
        base = {"sessionId": "s1", "promptId": "p1"}
        (failure,) = grok_build.parse("StopFailure", dict(
            base, error="429 from /Users/alice/proj", errorDetails="ERROR_DETAILS /Users/alice/x"))
        self.assertEqual((failure.status_message, failure.attributes["grok_build.stop.error"]),
                         ("unknown", "unknown"))
        self.assertEqual(failure.error_message, "ERROR_DETAILS /Users/alice/x")  # content, opt-in only
        (stop,) = grok_build.parse("Stop", dict(base, reason="stopped in /Users/alice/proj"))
        self.assertNotIn("grok_build.stop.reason", stop.attributes)
        (end,) = grok_build.parse("SessionEnd", dict(base, reason="shutdown"))
        self.assertEqual(end.attributes["grok_build.session.end_reason"], "shutdown")
        (tool,) = grok_build.parse("PostToolUse", dict(
            base, toolName="run_terminal_command", toolUseId="t1",
            toolResult={"exit_code": 0, "signal": "killed by /Users/alice/x", "timed_out": False}))
        self.assertNotIn("grok_build.tool.signal", tool.attributes)
        self.assertEqual(tool.status, OK)

    def test_missing_session_id_is_dropped(self):
        payload = {"hook_event_name": "PostToolUse", "toolName": "read_file", "toolUseId": "x", "durationMs": 3}
        self.assertEqual(grok_build.parse("PostToolUse", payload), [])
        self.assertTrue(grok_build.parse("PostToolUse", dict(payload, sessionId="s1")))


if __name__ == "__main__":
    unittest.main()
