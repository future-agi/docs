#!/usr/bin/env python3
"""Run otel-collector.yaml in a real otelcol-contrib and check what it forwards.

The input is rebuilt from the recorded goose 1.54.0 fixtures (span names,
parents, attribute keys): every "<present>" value becomes a placeholder, the
OS user name and host name goose exports become "fixture-user" and
"fixture-host", and each span gets goose's real log-line span events. The Future AGI exporter is swapped for a file exporter
(collector-test-overrides.yaml); everything else is the shipped config.

    OTELCOL_BIN=/path/to/otelcol-contrib python3 test_collector.py

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

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "otel-collector.yaml"
OVERRIDES = ROOT / "collector-test-overrides.yaml"
DEFAULT = json.loads((ROOT / "fixtures" / "goose-1.54.0-default.json").read_text())
CONTENT = json.loads((ROOT / "fixtures" / "goose-1.54.0-content.json").read_text())
OTELCOL = os.environ.get("OTELCOL_BIN") or shutil.which("otelcol-contrib")
IDENTITY = {"user.name": "fixture-user", "session.user": "fixture-user",
            "host.name": "fixture-host", "session.host": "fixture-host"}


def kv(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": value}}


def otlp_payload(fixture: dict) -> bytes:
    """OTLP/JSON request with the fixture's tree and keys; placeholders for values."""
    resource = [kv(k, IDENTITY.get(k, "fixture-" + k)) for k in fixture["resource_attribute_keys"]]
    ids = {}
    for i, span in enumerate(fixture["spans"]):
        ids.setdefault(span["name"], "%016x" % (i + 1))
    spans = []
    for i, span in enumerate(fixture["spans"]):
        attrs = []
        for key, value in span["attributes"].items():
            if value == "<present>":
                value = IDENTITY.get(key, "FIXTURE-VALUE " + key)
            attrs.append(kv(key, str(value)))
        out = {
            "traceId": "%032x" % (span["trace"] + 1),
            "spanId": "%016x" % (i + 1),
            "name": span["name"],
            "kind": 1,
            "startTimeUnixNano": str(1792000000000000000 + i * 1000),
            "endTimeUnixNano": str(1792000000000000000 + i * 1000 + 500),
            "attributes": attrs,
            # goose attaches its log lines as span events; this one is real 1.54.0 output.
            "events": [{"timeUnixNano": str(1792000000000000000 + i * 1000 + 1),
                        "name": 'Loading config from: "/Users/fixture-user/.config/goose/config.yaml"'},
                       {"timeUnixNano": str(1792000000000000000 + i * 1000 + 2), "name": "WAITING_LLM_STREAM_START"}],
        }
        if span["parent"]:
            out["parentSpanId"] = ids[span["parent"]]
        spans.append(out)
    body = {"resourceSpans": [{"resource": {"attributes": resource},
                               "scopeSpans": [{"scope": {"name": "goose"}, "spans": spans}]}]}
    return json.dumps(body).encode()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def attrs(items) -> dict:
    return {a["key"]: next(iter(a["value"].values())) if a["value"] else None for a in items or []}


@unittest.skipUnless(OTELCOL, "otelcol-contrib not found (set OTELCOL_BIN)")
class CollectorTest(unittest.TestCase):
    def run_collector(self, fixture: dict):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        out = Path(tmp) / "out.json"
        port = free_port()
        env = dict(os.environ, GOOSE_OTLP_LISTEN="127.0.0.1:%d" % port, TEST_OUT=str(out),
                   FI_API_KEY="test-key", FI_SECRET_KEY="test-secret", FI_PROJECT_NAME="goose-test")
        proc = subprocess.Popen([OTELCOL, "--config", "file:" + str(CONFIG), "--config", "file:" + str(OVERRIDES)],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(proc.stderr.close)
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        body = otlp_payload(fixture)
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
        spans = []
        for line in text.splitlines():
            for rs in json.loads(line)["resourceSpans"]:
                resource = attrs(rs["resource"]["attributes"])
                for ss in rs["scopeSpans"]:
                    for span in ss["spans"]:
                        spans.append((resource, span))
        return text, spans

    def test_identity_removed_and_agent_spans_labelled(self):
        text, spans = self.run_collector(DEFAULT)
        self.assertNotIn("fixture-user", text)
        self.assertNotIn("fixture-host", text)
        self.assertNotIn("/Users/", text)
        self.assertEqual(len(spans), len(DEFAULT["spans"]))
        for resource, span in spans:
            self.assertEqual(resource["project_name"], "goose-test")
            self.assertEqual(resource["project_type"], "observe")
            self.assertEqual(resource["service.name"], "fixture-service.name")
            self.assertNotIn("user.name", resource)
            self.assertNotIn("host.name", resource)
            a = attrs(span["attributes"])
            self.assertNotIn("session.user", a)
            self.assertNotIn("session.host", a)
            self.assertIn("session.id", a)
            self.assertEqual(span.get("events", []), [], "log-line span events are dropped")
            kind = a.get("gen_ai.span.kind")
            if a.get("gen_ai.operation.name") == "invoke_agent":
                self.assertEqual(kind, "AGENT", span["name"])
            else:
                self.assertIsNone(kind, span["name"])
        names = {span["name"] for _, span in spans}
        self.assertTrue({"reply", "reply_stream", "stream_response_from_provider", "dispatch_tool_call"} <= names)
        chat = [attrs(s["attributes"]) for _, s in spans if s["name"] == "stream_response_from_provider"]
        self.assertTrue(all(a["gen_ai.request.model"] == "gpt-6-luna" for a in chat))

    def test_content_opt_in_passes_through(self):
        # Content is goose's own switch; the collector forwards whatever goose sends.
        text, spans = self.run_collector(CONTENT)
        self.assertIn("FIXTURE-VALUE gen_ai.input.messages", text)
        self.assertIn("FIXTURE-VALUE gen_ai.tool.call.arguments", text)
        self.assertNotIn("fixture-user", text)
        self.assertNotIn("fixture-host", text)


if __name__ == "__main__":
    unittest.main()
