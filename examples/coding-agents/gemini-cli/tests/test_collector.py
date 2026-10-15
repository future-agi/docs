"""Run otel-collector.yaml in a real otelcol-contrib and check what it forwards.

The input is spans recorded from Gemini CLI 0.64.0 with content capture on
(``logPrompts: true``), with the content values replaced by a marker
(tests/fixtures/gemini-cli-0.64.0-traces.json). Appended to that: two error
spans, an ``llm_call`` that failed with a Gemini API error (status message,
exception event and stack trace from a real 0.64.0 run, install path rewritten
to /Users/fixture-user) and a synthetic ``tool_call`` that threw an fs error
with a local path in its message; and the ``user_prompt`` turn span with its
``system_prompt`` follow-up child from a real interactive 0.64.0 session
(session id replaced). Gemini CLI puts no content on those two even with
``logPrompts: true``. The Future AGI exporter is swapped for a file
exporter (tests/collector-test-overrides.yaml); everything else is the shipped
config.

    OTELCOL_BIN=/path/to/otelcol-contrib python3 -m unittest discover -s tests

Skipped when no otelcol-contrib binary is found.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "otel-collector.yaml"
OVERRIDES = HERE / "collector-test-overrides.yaml"
FIXTURE = HERE / "fixtures" / "gemini-cli-0.64.0-traces.json"
MARKER = "FIXTURE-CONTENT-MARKER"
# Added by Node's process and host resource detectors when
# OTEL_NODE_RESOURCE_DETECTORS is not set to env: paths, user and machine name.
LOCAL_IDENTITY = ("process.command_args", "process.command", "process.executable.path",
                  "process.executable.name", "process.owner", "host.name", "host.id")
OTELCOL = os.environ.get("OTELCOL_BIN") or shutil.which("otelcol-contrib")
CONTENT_KEYS = ("gen_ai.input.messages", "gen_ai.output.messages", "input.value",
                "output.value", "gen_ai.system_instructions", "gen_ai.tool.definitions")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ShippedConfigTest(unittest.TestCase):
    def test_collector_metrics_off_and_uncompressed(self):
        text = CONFIG.read_text()
        # Port 8888 (the collector's own metrics) collides with Jupyter or a
        # second collector; Future AGI answers gzip with HTTP 400.
        self.assertRegex(text, r"(?m)^service:\n  telemetry:\n    metrics:\n      level: none$")
        self.assertRegex(text, r"(?m)^    compression: none$")
        self.assertNotIn("level: none", OVERRIDES.read_text())


def attrs(items):
    out = {}
    for a in items or []:
        value = a["value"]
        out[a["key"]] = next(iter(value.values())) if value else None
    return out


@unittest.skipUnless(OTELCOL, "otelcol-contrib not found (set OTELCOL_BIN)")
class CollectorTest(unittest.TestCase):
    def run_collector(self, *extra_config: str):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        out = Path(tmp) / "out.json"
        port = free_port()
        env = dict(os.environ, GEMINI_OTLP_LISTEN="127.0.0.1:%d" % port, TEST_OUT=str(out),
                   FI_API_KEY="test-key", FI_SECRET_KEY="test-secret", FI_PROJECT_NAME="gemini-cli-test")
        args = [OTELCOL, "--config", "file:" + str(CONFIG), "--config", "file:" + str(OVERRIDES)]
        for item in extra_config:
            args += ["--set", item]
        proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(proc.stderr.close)
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        body = FIXTURE.read_bytes()
        for _ in range(100):
            try:
                req = urllib.request.Request("http://127.0.0.1:%d/v1/traces" % port, data=body,
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2).read()
                break
            except OSError:
                if proc.poll() is not None:
                    self.fail("collector exited: " + proc.stderr.read().decode()[-2000:])
                time.sleep(0.2)
        for _ in range(100):
            if out.exists() and out.stat().st_size:
                break
            time.sleep(0.2)
        text = out.read_text()
        self.assertTrue(text, "collector wrote nothing")
        return text, [json.loads(line) for line in text.splitlines() if line.strip()]

    def spans(self, requests):
        result = []
        for req in requests:
            for rs in req["resourceSpans"]:
                resource = attrs(rs["resource"]["attributes"])
                for ss in rs["scopeSpans"]:
                    for span in ss["spans"]:
                        result.append((resource, span["name"], attrs(span["attributes"])))
        return result

    def raw_spans(self, requests):
        return {span["spanId"]: span for req in requests for rs in req["resourceSpans"]
                for ss in rs["scopeSpans"] for span in ss["spans"]}

    def test_default_strips_content_and_labels_kinds(self):
        text, requests = self.run_collector()
        self.assertNotIn(MARKER, text)
        self.assertNotIn("/Users/", text)
        self.assertNotIn("fixture-user", text)
        self.assertNotIn("file://", text)
        self.assertNotIn("NOT_FOUND", text)  # the API error body
        spans = self.spans(requests)
        self.assertEqual(len(spans), 9)
        kinds = {}
        for resource, name, a in spans:
            self.assertEqual(resource["project_name"], "gemini-cli-test")
            for key in LOCAL_IDENTITY:
                self.assertNotIn(key, resource)
            self.assertEqual(resource["host.arch"], "arm64")
            self.assertEqual(resource["process.runtime.name"], "nodejs")
            for key in CONTENT_KEYS:
                self.assertNotIn(key, a)
            self.assertEqual(a["gen_ai.conversation.id"], "fixture-session-0001")
            self.assertEqual(a["session.id"], "fixture-session-0001")
            kinds.setdefault(name, set()).add(a.get("gen_ai.span.kind"))
        # user_prompt / system_prompt: interactive mode's turn spans.
        self.assertEqual(kinds, {"llm_call": {"LLM"}, "list_directory": {"TOOL"},
                                 "read_file": {"TOOL"}, "schedule_tool_calls": {"CHAIN"},
                                 "user_prompt": {"CHAIN"}, "system_prompt": {"CHAIN"}})
        raw = self.raw_spans(requests)
        turn, follow_up = raw["6e5f4a3b2c1d0e01"], raw["6e5f4a3b2c1d0e02"]
        self.assertEqual((turn["name"], follow_up["name"]), ("user_prompt", "system_prompt"))
        self.assertFalse(turn.get("parentSpanId"))
        self.assertEqual(follow_up["parentSpanId"], turn["spanId"])
        ok_llm = [attrs(s["attributes"]) for s in raw.values()
                  if s["name"] == "llm_call" and s["status"].get("code") == 1]
        self.assertEqual(len(ok_llm), 2)
        self.assertTrue(all(a["gen_ai.request.model"] == "gemini-3.8-flash" for a in ok_llm))
        self.assertTrue(all(int(a["gen_ai.usage.input_tokens"]) > 0 for a in ok_llm))
        # Errors stay ERROR; only the error class (plus the HTTP status of a
        # Gemini API error) is kept, not the message or the stack trace.
        api_error, tool_error = raw["9b8a7c6d5e4f3a21"], raw["9b8a7c6d5e4f3a22"]
        self.assertEqual(api_error["status"], {"code": 2, "message": "ApiError HTTP 404"})
        self.assertEqual(tool_error["status"], {"code": 2, "message": "ENOENT"})
        for span, error_type in ((api_error, "ApiError"), (tool_error, "ENOENT")):
            self.assertEqual([(e["name"], attrs(e["attributes"])) for e in span["events"]],
                             [("exception", {"exception.type": error_type})])
        for span in raw.values():
            if span["status"].get("code") != 2:
                self.assertFalse(span["status"].get("message"))

    def test_opt_in_pipeline_keeps_messages(self):
        # The documented opt-in: drop transform/strip-content from the pipeline.
        text, requests = self.run_collector(
            "service.pipelines.traces.processors=[transform/gemini-cli,batch]")
        self.assertIn(MARKER + " gen_ai.input.messages", text)
        self.assertIn(MARKER + " gen_ai.output.messages", text)
        for _, name, a in self.spans(requests):
            if name in ("user_prompt", "system_prompt"):
                # Gemini CLI 0.64.0 records no content on its turn spans.
                self.assertEqual(a["gen_ai.span.kind"], "CHAIN")
                self.assertNotIn("input.value", a)
                continue
            self.assertIn("gen_ai.input.messages", a["input.value"])
            if "gen_ai.output.messages" in a:  # a failed model call has no output
                self.assertIn("gen_ai.output.messages", a["output.value"])
        # Error text is content: kept with the opt-in. Stack traces are not
        # (install paths only), with or without it.
        raw = self.raw_spans(requests)
        self.assertIn("NOT_FOUND", raw["9b8a7c6d5e4f3a21"]["status"]["message"])
        self.assertIn("FIXTURE-CONTENT-MARKER.txt", raw["9b8a7c6d5e4f3a22"]["status"]["message"])
        event = attrs(raw["9b8a7c6d5e4f3a22"]["events"][0]["attributes"])
        self.assertEqual(sorted(event), ["exception.message", "exception.type"])
        self.assertNotIn("file://", text)
        # The command line, executable paths, user and machine name are removed
        # either way. (The opted-in tool error message above carries a path.)
        self.assertNotIn("prompt on the command line", text)
        self.assertNotIn("fixture-users-laptop", text)
        self.assertNotIn(".nvm", text)
        for resource, _, _ in self.spans(requests):
            for key in LOCAL_IDENTITY:
                self.assertNotIn(key, resource)
        # The opt-in exports the system prompt and tool schemas (documented).
        self.assertIn(MARKER + " gen_ai.system_instructions", text)


if __name__ == "__main__":
    unittest.main()
