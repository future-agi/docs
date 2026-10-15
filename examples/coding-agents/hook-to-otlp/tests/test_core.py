"""Emitter core tests: ids, pairing, parenting, privacy, transport, failure modes."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

from tests.helpers import Receiver, all_spans, attrs, base_env, config, latest, run_cli

import emit
from adapters.base import END, ERROR, INSTANT, LLM, OK, SESSION, START, TOOL, TURN, UPDATE, SpanEvent

T0 = 1_800_000_000_000_000_000
MS = 1_000_000


def fake_adapter(handler):
    module = types.ModuleType("adapters.fake")
    module.APP = "fake"
    module.DISPLAY_NAME = "Fake"
    module.parse = handler
    return module


def scripted(events_by_hook):
    """Adapter whose parse() returns a fixed list of SpanEvents per hook name."""
    return fake_adapter(lambda event, payload: list(events_by_hook.get(event, [])))


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = config("fake", self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hooks(self, adapter, hooks, cfg=None):
        cfg = cfg or self.cfg
        spans = []
        for offset_ms, hook in hooks:
            spans.extend(emit.build_spans(adapter, cfg, hook, {}, now_ns=T0 + offset_ms * MS))
        return spans

    def test_trace_and_span_ids_are_deterministic(self):
        self.assertEqual(emit.trace_id("cursor", "s1"), emit.trace_id("cursor", "s1"))
        self.assertNotEqual(emit.trace_id("cursor", "s1"), emit.trace_id("cursor", "s2"))
        self.assertNotEqual(emit.trace_id("cursor", "s1"), emit.trace_id("codex", "s1"))
        self.assertEqual(len(emit.trace_id("a", "b")), 32)
        self.assertEqual(len(emit.span_id("a", "b", TOOL, "k")), 16)

    def test_session_turn_tool_hierarchy_and_pairing(self):
        adapter = scripted({
            "s": [SpanEvent(START, SESSION, "S")],
            "t0": [SpanEvent(START, TURN, "S", key="g1", model="m-1")],
            "pre": [SpanEvent(START, TOOL, "S", key="call-1", turn_id="g1", name="Shell")],
            "post": [SpanEvent(END, TOOL, "S", key="call-1", turn_id="g1", status=OK)],
            "t1": [SpanEvent(END, TURN, "S", key="g1", status=OK)],
            "e": [SpanEvent(END, SESSION, "S")],
        })
        spans = self.run_hooks(adapter, [(0, "s"), (100, "t0"), (200, "pre"), (700, "post"), (900, "t1"), (1000, "e")])
        trace = emit.trace_id("fake", "S")
        self.assertTrue(all(s["traceId"] == trace for s in spans))
        root_id = emit.span_id("fake", "S", SESSION, "")
        turn_id = emit.span_id("fake", "S", TURN, "g1")
        tool = [s for s in spans if s["name"] == "Shell"][0]
        self.assertEqual(tool["parentSpanId"], turn_id)
        self.assertEqual(int(tool["endTimeUnixNano"]) - int(tool["startTimeUnixNano"]), 500 * MS)
        self.assertEqual(attrs(tool)["fi.span.kind"], "TOOL")
        self.assertEqual(attrs(tool)["gen_ai.tool.call.id"], "call-1")
        turn = [s for s in spans if s["spanId"] == turn_id][0]
        self.assertEqual(turn["parentSpanId"], root_id)
        self.assertEqual(int(turn["endTimeUnixNano"]) - int(turn["startTimeUnixNano"]), 800 * MS)
        self.assertEqual(attrs(turn)["llm.model_name"], "m-1")
        root = latest(spans, root_id)
        self.assertNotIn("parentSpanId", root)
        self.assertEqual(int(root["endTimeUnixNano"]) - int(root["startTimeUnixNano"]), 1000 * MS)
        self.assertEqual(attrs(root)["session.id"], "S")
        # Every root export reuses the same start, so the backend upserts it.
        starts = {s["startTimeUnixNano"] for s in spans if s["spanId"] == root_id}
        self.assertEqual(len(starts), 1)
        # Session end removes the state file.
        self.assertEqual(list(self.cfg.state_dir.glob("*.json")), [])

    def test_root_rides_along_with_every_child_export(self):
        adapter = scripted({
            "s": [SpanEvent(START, SESSION, "S")],
            "tool": [SpanEvent(END, TOOL, "S", key="c1", name="Shell")],
        })
        self.assertEqual(self.run_hooks(adapter, [(0, "s")]), [], "session start alone exports nothing")
        spans = self.run_hooks(adapter, [(500, "tool")])
        root_id = emit.span_id("fake", "S", SESSION, "")
        self.assertEqual([s["spanId"] for s in spans][-1], root_id)
        self.assertEqual(int(spans[-1]["startTimeUnixNano"]), T0)

    def test_session_without_activity_exports_nothing(self):
        adapter = scripted({
            "s": [SpanEvent(START, SESSION, "S")],
            "e": [SpanEvent(END, SESSION, "S", duration_ms=0)],
        })
        self.assertEqual(self.run_hooks(adapter, [(0, "s"), (10, "e")]), [])
        self.assertEqual(list(self.cfg.state_dir.glob("*.json")), [])

    def test_keyless_turns_get_per_session_keys(self):
        # Apps without turn ids (Kiro, Antigravity): START mints turn-N, END/UPDATE use the open turn.
        adapter = scripted({
            "prompt": [SpanEvent(START, TURN, "S", input="P")],
            "tool": [SpanEvent(END, TOOL, "S", name="Shell", duration_ms=100)],
            "reply": [SpanEvent(UPDATE, TURN, "S", output="R")],
            "stop": [SpanEvent(END, TURN, "S", status=OK)],
        })
        spans = self.run_hooks(adapter, [(0, "prompt"), (500, "tool"), (600, "reply"), (700, "stop"),
                                         (800, "prompt"), (900, "stop"), (950, "stop")])
        turn1 = emit.span_id("fake", "S", TURN, "turn-1")
        turn2 = emit.span_id("fake", "S", TURN, "turn-2")
        tool = [s for s in spans if s["name"] == "Shell"][0]
        self.assertEqual(tool["parentSpanId"], turn1)
        t1 = latest(spans, turn1)
        self.assertEqual(int(t1["endTimeUnixNano"]) - int(t1["startTimeUnixNano"]), 700 * MS)
        self.assertEqual(attrs(t1)["coding_agent.turn.id"], "turn-1")
        t2 = latest(spans, turn2)
        self.assertEqual(int(t2["endTimeUnixNano"]) - int(t2["startTimeUnixNano"]), 100 * MS)
        # The extra stop has no open turn and is ignored.
        self.assertEqual(len([s for s in spans if s["spanId"] in (turn1, turn2)]), 2)

    def test_keyless_tool_end_pairs_with_oldest_start_of_same_name(self):
        # Apps whose pre/post tool hooks carry no call id: FIFO by tool name.
        adapter = scripted({
            "pre-read": [SpanEvent(START, TOOL, "S", turn_id="g", name="Read")],
            "pre-shell": [SpanEvent(START, TOOL, "S", turn_id="g", name="Shell")],
            "post-read": [SpanEvent(END, TOOL, "S", turn_id="g", name="Read")],
            "post-shell": [SpanEvent(END, TOOL, "S", turn_id="g", name="Shell", status=ERROR)],
        })
        spans = self.run_hooks(adapter, [(0, "pre-read"), (100, "pre-read"), (200, "pre-shell"),
                                         (300, "post-read"), (400, "post-shell"), (450, "post-read")])
        reads = [s for s in spans if s["name"] == "Read"]
        self.assertEqual([int(s["endTimeUnixNano"]) - int(s["startTimeUnixNano"]) for s in reads],
                         [300 * MS, 350 * MS])
        shell = [s for s in spans if s["name"] == "Shell"][0]
        self.assertEqual(int(shell["endTimeUnixNano"]) - int(shell["startTimeUnixNano"]), 200 * MS)
        self.assertEqual(shell["status"]["code"], 2)
        self.assertNotIn("gen_ai.tool.call.id", attrs(shell))

    def test_turn_start_closes_other_open_turn_and_late_end_corrects_it(self):
        adapter = scripted({
            "t1": [SpanEvent(START, TURN, "S", key="g1")],
            "tool1": [SpanEvent(START, TOOL, "S", key="c1", turn_id="g1", name="Shell")],
            "t2": [SpanEvent(START, TURN, "S", key="g2")],
            "end1": [SpanEvent(END, TURN, "S", key="g1", status=OK)],
            "end2": [SpanEvent(END, TURN, "S", key="g2")],
        })
        first = self.run_hooks(adapter, [(0, "t1"), (100, "tool1"), (500, "t2")])
        g1 = emit.span_id("fake", "S", TURN, "g1")
        incomplete = latest(first, g1)
        self.assertTrue(attrs(incomplete)["coding_agent.incomplete"])
        tool = [s for s in first if s["name"] == "Shell"][0]
        self.assertTrue(attrs(tool)["coding_agent.incomplete"], "children of the closed turn are closed too")
        # A late end for g1 re-sends it complete, same id and start, without the incomplete flag.
        late = self.run_hooks(adapter, [(600, "end1")])
        corrected = latest(late, g1)
        self.assertEqual(corrected["startTimeUnixNano"], incomplete["startTimeUnixNano"])
        self.assertNotIn("coding_agent.incomplete", attrs(corrected))
        self.assertEqual(corrected["status"]["code"], 1)
        # g2 is still the open turn.
        rest = self.run_hooks(adapter, [(900, "end2")])
        g2 = latest(rest, emit.span_id("fake", "S", TURN, "g2"))
        self.assertEqual(int(g2["endTimeUnixNano"]) - int(g2["startTimeUnixNano"]), 400 * MS)

    def test_empty_response_prints_nothing(self):
        module = types.ModuleType("adapters.fake_quiet")
        module.APP, module.DISPLAY_NAME = "fake_quiet", "Quiet"
        module.parse = lambda event, payload: []
        module.respond = lambda event, payload: ""
        sys.modules["adapters.fake_quiet"] = module
        try:
            self.assertEqual(emit.run(["fake_quiet", "UserPromptSubmit"], "{}", {}), "")
            module.respond = lambda event, payload: None
            self.assertEqual(emit.run(["fake_quiet", "UserPromptSubmit"], "{}", {}), "{}")
        finally:
            del sys.modules["adapters.fake_quiet"]

    def test_end_without_start_uses_vendor_duration(self):
        adapter = scripted({"post": [SpanEvent(END, TOOL, "S", key="c", name="Read", duration_ms=250)]})
        spans = self.run_hooks(adapter, [(1000, "post")])
        tool = spans[0]
        self.assertEqual(int(tool["endTimeUnixNano"]) - int(tool["startTimeUnixNano"]), 250 * MS)
        # No turn known -> parented to the session root.
        self.assertEqual(tool["parentSpanId"], emit.span_id("fake", "S", SESSION, ""))

    def test_tool_uses_current_turn_when_turn_id_missing(self):
        adapter = scripted({
            "t0": [SpanEvent(START, TURN, "S", key="g7")],
            "tool": [SpanEvent(INSTANT, TOOL, "S", name="Grep")],
        })
        spans = self.run_hooks(adapter, [(0, "t0"), (10, "tool")])
        self.assertEqual(spans[0]["parentSpanId"], emit.span_id("fake", "S", TURN, "g7"))

    def test_turn_auto_opens_and_root_upserts_on_turn_end(self):
        adapter = scripted({
            "tool": [SpanEvent(END, TOOL, "S", key="c1", turn_id="g1", name="Shell", duration_ms=300)],
            "stop": [SpanEvent(END, TURN, "S", key="g1")],
        })
        spans = self.run_hooks(adapter, [(1000, "tool"), (2000, "stop")])
        turn = [s for s in spans if s["spanId"] == emit.span_id("fake", "S", TURN, "g1")][0]
        # Turn starts when its first child started.
        self.assertEqual(int(turn["startTimeUnixNano"]), T0 + 700 * MS)
        root = latest(spans, emit.span_id("fake", "S", SESSION, ""))
        self.assertIsNotNone(root, "root must be exported at turn end even without a session hook")
        self.assertEqual(int(root["startTimeUnixNano"]), T0 + 700 * MS)

    def test_open_children_are_closed_as_incomplete_at_turn_end(self):
        adapter = scripted({
            "pre": [SpanEvent(START, TOOL, "S", key="c9", turn_id="g1", name="Shell")],
            "stop": [SpanEvent(END, TURN, "S", key="g1")],
        })
        spans = self.run_hooks(adapter, [(0, "pre"), (50, "stop")])
        tool = [s for s in spans if s["name"] == "Shell"][0]
        self.assertTrue(attrs(tool)["coding_agent.incomplete"])

    def test_error_status_and_message_privacy(self):
        adapter = scripted({"fail": [SpanEvent(END, TOOL, "S", key="c", name="Shell", status=ERROR,
                                               status_message="timeout", error_message="secret detail")]})
        span = self.run_hooks(adapter, [(0, "fail")])[0]
        self.assertEqual(span["status"], {"code": 2, "message": "timeout"})
        self.assertNotIn("secret detail", json.dumps(span))

    def test_content_dropped_by_default_and_kept_on_opt_in(self):
        events = {
            "t0": [SpanEvent(START, TURN, "S", key="g", input="PROMPT_MARK")],
            "tool": [SpanEvent(END, TOOL, "S", key="c", turn_id="g", name="Shell",
                               input={"command": "echo ARG_MARK"}, output="OUT_MARK")],
            "resp": [SpanEvent(UPDATE, TURN, "S", key="g", output="RESP_MARK")],
            "stop": [SpanEvent(END, TURN, "S", key="g")],
        }
        hooks = [(0, "t0"), (10, "tool"), (20, "resp"), (30, "stop")]
        off = json.dumps(self.run_hooks(scripted(events), hooks))
        for marker in ("PROMPT_MARK", "ARG_MARK", "OUT_MARK", "RESP_MARK", "input.value", "output.value"):
            self.assertNotIn(marker, off)
        with tempfile.TemporaryDirectory() as other:
            cfg = config("fake", other, FI_HOOK_CAPTURE_CONTENT="1")
            on = self.run_hooks(scripted(events), hooks, cfg=cfg)
        turn = [s for s in on if s["spanId"] == emit.span_id("fake", "S", TURN, "g")][0]
        self.assertEqual(attrs(turn)["input.value"], "PROMPT_MARK")
        self.assertEqual(attrs(turn)["output.value"], "RESP_MARK")
        tool = [s for s in on if s["name"] == "Shell"][0]
        self.assertIn("ARG_MARK", attrs(tool)["input.value"])

    def test_redaction_and_truncation(self):
        text = "key sk-abcdefghijklmnopqrstuv and Bearer abcdefghijklmnop api_key=xyz123 " + "x" * 50
        rendered = emit.render_content(text, max_chars=60)
        self.assertNotIn("sk-abcdefghijklmnopqrstuv", rendered)
        self.assertNotIn("abcdefghijklmnop api", rendered)
        self.assertIn("[truncated", rendered)
        self.assertIn("[REDACTED]", emit.render_content({"password": "hunter22"}, 0))

    def test_events_without_session_are_dropped(self):
        adapter = scripted({"x": [SpanEvent(INSTANT, LLM, "", name="nope")]})
        self.assertEqual(self.run_hooks(adapter, [(0, "x")]), [])

    def test_state_sweep_removes_old_files(self):
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        old = self.cfg.state_dir / "old.json"
        old.write_text("{}")
        os.utime(old, (time.time() - 3 * 86400,) * 2)
        emit.sweep_state(self.cfg)
        self.assertFalse(old.exists())

    def test_attribute_encoding(self):
        encoded = {a["key"]: a["value"] for a in emit.otlp_attributes(
            {"b": True, "i": 3, "f": 1.5, "s": "x", "l": ["a", 1], "n": None})}
        self.assertEqual(encoded["b"], {"boolValue": True})
        self.assertEqual(encoded["i"], {"intValue": "3"})
        self.assertEqual(encoded["f"], {"doubleValue": 1.5})
        self.assertEqual(encoded["l"]["arrayValue"]["values"][1], {"intValue": "1"})
        self.assertNotIn("n", encoded)

    def test_env_file_fills_missing_keys_only(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write("# comment\nexport FI_API_KEY='from-file'\nFI_PROJECT_NAME=p\nOTHER=ignored\n")
        env = {"FI_API_KEY": "from-env"}
        emit.load_env_file(handle.name, env)
        os.unlink(handle.name)
        self.assertEqual(env, {"FI_API_KEY": "from-env", "FI_PROJECT_NAME": "p"})


class CliTest(unittest.TestCase):
    """End-to-end through the real CLI with the Cursor adapter and a loopback receiver."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rx = Receiver()

    def tearDown(self):
        self.rx.close()
        self.tmp.cleanup()

    def payload(self, **extra):
        p = {"conversation_id": "cli-1", "generation_id": "g1", "hook_event_name": "postToolUse",
             "tool_name": "Shell", "tool_use_id": "t1", "duration": 10, "tool_input": {"command": "ls"}}
        p.update(extra)
        return p

    def test_sync_export_headers_resource_and_stdout(self):
        env = base_env(self.tmp.name, endpoint=self.rx.url + "/tracer/v1/traces")
        result = run_cli(["cursor", "postToolUse"], self.payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "{}")
        self.assertEqual(len(self.rx.requests), 1)
        path, headers, body = self.rx.requests[0]
        self.assertEqual(path, "/tracer/v1/traces")
        self.assertEqual(headers["X-Api-Key"], "test-api-key")
        self.assertEqual(headers["X-Secret-Key"], "test-secret-key")
        resource = attrs(body["resourceSpans"][0]["resource"])
        self.assertEqual(resource["project_name"], "hook-test")
        self.assertEqual(resource["service.name"], "cursor")
        self.assertFalse(resource["coding_agent.content_captured"])

    def test_base_url_gets_traces_path(self):
        env = base_env(self.tmp.name, FI_BASE_URL=self.rx.url)
        del env["FI_OTLP_ENDPOINT"]
        run_cli(["cursor", "postToolUse"], self.payload(), env)
        self.assertEqual(self.rx.requests[0][0], "/tracer/v1/traces")

    def test_background_send_returns_before_network(self):
        env = base_env(self.tmp.name, endpoint=self.rx.url + "/v1/traces")
        del env["FI_HOOK_SYNC"]
        result = run_cli(["cursor", "postToolUse"], self.payload(), env)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "{}"))
        self.rx.wait_for(1)
        self.assertEqual(sorted(sp["name"] for sp in self.rx.spans()), ["Cursor session", "Shell"])

    def test_unreachable_collector_is_fast_and_silent(self):
        env = base_env(self.tmp.name, endpoint="http://127.0.0.1:9/v1/traces",
                       FI_HOOK_LOG_FILE=os.path.join(self.tmp.name, "hook.log"))
        started = time.monotonic()
        result = run_cli(["cursor", "postToolUse"], self.payload(), env)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual((result.returncode, result.stdout.strip(), result.stderr), (0, "{}", ""))
        log = Path(self.tmp.name, "hook.log").read_text()
        self.assertIn("error=", log)
        self.assertNotIn("test-api-key", log)

    def test_collector_error_status_is_swallowed(self):
        bad = Receiver(status=500)
        try:
            env = base_env(self.tmp.name, endpoint=bad.url + "/v1/traces")
            result = run_cli(["cursor", "postToolUse"], self.payload(), env)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, "{}"))
        finally:
            bad.close()

    def test_garbage_input_still_answers_host(self):
        env = base_env(self.tmp.name, endpoint=self.rx.url + "/v1/traces")
        for stdin in ("", "not json", "[1,2]"):
            result = run_cli(["cursor", "beforeSubmitPrompt"], stdin, env)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, '{"continue": true}'))
        result = run_cli(["no-such-app"], "{}", env)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "{}"))
        self.assertEqual(self.rx.requests, [])

    def test_missing_credentials_is_a_noop(self):
        env = base_env(self.tmp.name, endpoint=self.rx.url + "/v1/traces")
        del env["FI_API_KEY"]
        result = run_cli(["cursor", "postToolUse"], self.payload(), env)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "{}"))
        self.assertEqual(self.rx.requests, [])

    def test_disabled_switch(self):
        env = base_env(self.tmp.name, endpoint=self.rx.url + "/v1/traces", FI_HOOK_DISABLED="1")
        run_cli(["cursor", "postToolUse"], self.payload(), env)
        self.assertEqual(self.rx.requests, [])

    def test_dump_file_matches_what_was_sent(self):
        dump = os.path.join(self.tmp.name, "dump.jsonl")
        env = base_env(self.tmp.name, endpoint=self.rx.url + "/v1/traces", FI_HOOK_DUMP_FILE=dump)
        run_cli(["cursor", "postToolUse"], self.payload(), env)
        dumped = [json.loads(line) for line in Path(dump).read_text().splitlines()]
        self.assertEqual(all_spans(dumped[0]), self.rx.spans())


if __name__ == "__main__":
    unittest.main()
