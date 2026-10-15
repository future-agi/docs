"""Run otel-collector.yaml in a real otelcol-contrib and check what it forwards.

The input is spans recorded from Gemini CLI 0.64.0 with content capture on
(``logPrompts: true``), with the content values replaced by a marker
(tests/fixtures/gemini-cli-0.64.0-traces.json). The Future AGI exporter is
swapped for a file exporter (tests/collector-test-overrides.yaml); everything
else is the shipped config.

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


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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

    def test_default_strips_content_and_labels_kinds(self):
        text, requests = self.run_collector()
        self.assertNotIn(MARKER, text)
        self.assertNotIn("/Users/", text)
        self.assertNotIn("fixture-user", text)
        spans = self.spans(requests)
        self.assertEqual(len(spans), 5)
        kinds = {}
        for resource, name, a in spans:
            self.assertEqual(resource["project_name"], "gemini-cli-test")
            for key in LOCAL_IDENTITY:
                self.assertNotIn(key, resource)
            self.assertEqual(resource["host.arch"], "arm64")
            self.assertEqual(resource["process.runtime.name"], "nodejs")
            for key in ("gen_ai.input.messages", "gen_ai.output.messages", "input.value",
                        "output.value", "gen_ai.system_instructions", "gen_ai.tool.definitions"):
                self.assertNotIn(key, a)
            self.assertEqual(a["gen_ai.conversation.id"], "fixture-session-0001")
            self.assertEqual(a["session.id"], "fixture-session-0001")
            kinds.setdefault(name, set()).add(a.get("gen_ai.span.kind"))
        self.assertEqual(kinds, {"llm_call": {"LLM"}, "list_directory": {"TOOL"},
                                 "read_file": {"TOOL"}, "schedule_tool_calls": {"CHAIN"}})
        llm = [a for _, name, a in spans if name == "llm_call"]
        self.assertTrue(all(a["gen_ai.request.model"] == "gemini-3.8-flash" for a in llm))
        self.assertTrue(all(int(a["gen_ai.usage.input_tokens"]) > 0 for a in llm))

    def test_opt_in_pipeline_keeps_messages(self):
        # The documented opt-in: drop transform/strip-content from the pipeline.
        text, requests = self.run_collector(
            "service.pipelines.traces.processors=[transform/gemini-cli,batch]")
        self.assertIn(MARKER + " gen_ai.input.messages", text)
        self.assertIn(MARKER + " gen_ai.output.messages", text)
        for _, _, a in self.spans(requests):
            self.assertIn("gen_ai.input.messages", a["input.value"])
            self.assertIn("gen_ai.output.messages", a["output.value"])
        # The command line, local paths, user and machine name are removed either way.
        self.assertNotIn("prompt on the command line", text)
        self.assertNotIn("fixture-user", text)
        # The opt-in exports the system prompt and tool schemas (documented).
        self.assertIn(MARKER + " gen_ai.system_instructions", text)


if __name__ == "__main__":
    unittest.main()
