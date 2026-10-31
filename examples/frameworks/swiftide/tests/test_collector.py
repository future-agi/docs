"""Real Swiftide -> released Collector -> OTLP protobuf receiver, localhost only."""
import argparse
import contextlib
import http.server
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

ROOT = Path(__file__).resolve().parents[1]
MARKER = "private-payload-7d08"
OPTIONS = None


def attributes(items):
    return {kv.key: getattr(kv.value, kv.value.WhichOneof("value")) for kv in items}


class Server(http.server.ThreadingHTTPServer):
    def __init__(self, handler):
        super().__init__(("127.0.0.1", 0), handler)
        self.items = []
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, body=b"", content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Sink(Handler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        request = ExportTraceServiceRequest.FromString(raw)
        with self.server.lock:
            self.server.items.append((self.path, dict(self.headers), raw, request))
        self.reply(200, content_type="application/x-protobuf")


class Model(Handler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.items.append(request)
        if request["model"] == "broken-model":
            self.reply(400, json.dumps({"error": {
                "message": MARKER + "-provider-error", "type": "invalid_request_error",
                "code": "model_not_found", "param": "model",
            }}).encode())
            return
        if len(self.server.items) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_weather", "type": "function", "function": {
                    "name": "get_weather", "arguments": json.dumps({"city": self.server.city})
                }
            }]}
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": MARKER + "-answer"}
            finish = "stop"
        self.reply(200, json.dumps({
            "id": "chatcmpl-local", "object": "chat.completion", "created": 1,
            "model": "fixture-model", "choices": [{"index": 0, "message": message,
                                                       "finish_reason": finish}],
            "usage": {"prompt_tokens": 21, "completion_tokens": 7, "total_tokens": 28},
        }).encode())


def model_env(server, model="fixture-model"):
    return {"PATH": os.defpath, "OPENAI_API_KEY": "fixture-provider-key",
            "OPENAI_BASE_URL": server.url + "/v1", "MODEL": model}


class Contract(unittest.TestCase):
    @contextlib.contextmanager
    def pipeline(self, capture=False):
        sink = Server(Sink)
        with tempfile.TemporaryDirectory() as directory:
            log = open(Path(directory) / "collector.log", "w+")
            env = {"PATH": os.defpath, "TMPDIR": tempfile.gettempdir(),
                   "FI_TRACES_ENDPOINT": sink.url + "/tracer/v1/traces",
                   "FI_API_KEY": "fixture-api-key", "FI_SECRET_KEY": "fixture-secret-key",
                   "FI_PROJECT_NAME": "swiftide-contract",
                   "FI_CAPTURE_CONTENT": str(capture).lower()}
            process = subprocess.Popen([OPTIONS.collector, "--config", str(ROOT / "collector.yaml")],
                                       env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        log.seek(0)
                        self.fail("Collector exited: " + log.read())
                    try:
                        with socket.create_connection(("127.0.0.1", 4318), timeout=0.1):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            self.fail("Collector did not listen on loopback")
                        time.sleep(0.05)
                yield sink
            except BaseException:
                log.flush()
                log.seek(0)
                print(log.read())
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=15)
                log.seek(0)
                output = log.read()
                log.close()
                sink.close()
                if process.returncode != 0:
                    self.fail("Collector failed: " + output)

    def wait_spans(self, sink, expected):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            spans = [s for _, _, _, req in list(sink.items)
                     for r in req.resource_spans for scope in r.scope_spans for s in scope.spans]
            if len(spans) >= expected:
                return spans
            time.sleep(0.05)
        self.fail(f"Only {len(spans)} spans exported, expected at least {expected}")

    def run_agent(self, capture=False, city="Paris", model="fixture-model"):
        with self.pipeline(capture) as sink:
            server = Server(Model)
            server.city = city
            try:
                result = subprocess.run([OPTIONS.binary, MARKER + "-question"], timeout=30,
                                        env=model_env(server, model), capture_output=True, text=True)
                self.assertEqual(result.returncode, 1 if model == "broken-model" else 0, result.stderr)
                spans = self.wait_spans(sink, 3)
                # Shutdown flushed Rust spans; terminating the Collector drains its batch.
            finally:
                server.close()
        spans = [s for _, _, _, req in sink.items for r in req.resource_spans
                 for scope in r.scope_spans for s in scope.spans]
        self.assert_wire(sink)
        return spans, b"".join(item[2] for item in sink.items)

    def assert_wire(self, sink):
        self.assertTrue(sink.items)
        for path, headers, raw, req in sink.items:
            headers = {k.lower(): v for k, v in headers.items()}
            self.assertEqual(path, "/tracer/v1/traces")
            self.assertEqual(headers["x-api-key"], "fixture-api-key")
            self.assertEqual(headers["x-secret-key"], "fixture-secret-key")
            self.assertEqual(headers["content-type"], "application/x-protobuf")
            self.assertNotIn("content-encoding", headers)
            for secret in [b"fixture-api-key", b"fixture-secret-key", b"fixture-provider-key"]:
                self.assertNotIn(secret, raw)
            for resource in req.resource_spans:
                attrs = attributes(resource.resource.attributes)
                self.assertEqual(attrs["project_name"], "swiftide-contract")
                self.assertEqual(attrs["project_type"], "observe")
                self.assertLessEqual(set(attrs), {"project_name", "project_type", "service.name"})
                for scope in resource.scope_spans:
                    self.assertFalse(scope.scope.attributes)
                    for span in scope.spans:
                        self.assertFalse(span.events)
                        self.assertFalse(span.links)
                        self.assertFalse(span.status.message)
                        self.assertFalse(span.trace_state)

    def test_semantics_parentage_and_default_privacy(self):
        spans, raw = self.run_agent()
        root, = [s for s in spans if s.name == "agent.query"]
        self.assertEqual(attributes(root.attributes)["fi.span.kind"], "AGENT")
        self.assertFalse(root.parent_span_id)
        self.assertTrue(all(s.trace_id == root.trace_id for s in spans))
        steps = [s for s in spans if s.name == "step"]
        self.assertEqual(len(steps), 2)
        self.assertTrue(all(s.parent_span_id == root.span_id for s in steps))
        llms = [s for s in spans if attributes(s.attributes)["fi.span.kind"] == "LLM"]
        self.assertEqual(len(llms), 2, "no duplicated provider spans")
        for span in llms:
            attrs = attributes(span.attributes)
            self.assertEqual(attrs["llm.model_name"], "fixture-model")
            self.assertEqual(attrs["llm.token_count.prompt"], 21)
            self.assertEqual(attrs["llm.token_count.completion"], 7)
            self.assertEqual(attrs["llm.token_count.total"], 28)
            self.assertIn(span.parent_span_id, [s.span_id for s in steps])
            kinds = {kv.key: kv.value.WhichOneof("value") for kv in span.attributes}
            self.assertEqual(kinds["llm.token_count.total"], "int_value")
        tools = [s for s in spans if attributes(s.attributes)["fi.span.kind"] == "TOOL"]
        self.assertEqual(len(tools), 1)
        self.assertIn(tools[0].parent_span_id, [s.span_id for s in steps])
        self.assertNotIn(MARKER.encode(), raw)
        self.assertNotIn(b"langfuse", raw)
        self.assertNotIn(b"code.file.path", raw)
        self.assertTrue(all(s.status.code == 0 for s in spans))

    def test_content_opt_in_is_structured_not_raw_events(self):
        spans, raw = self.run_agent(capture=True)
        self.assertIn((MARKER + "-question").encode(), raw)
        self.assertIn((MARKER + "-answer").encode(), raw)
        for span in spans:
            attrs = attributes(span.attributes)
            if attrs["fi.span.kind"] == "LLM":
                self.assertIn("messages", json.loads(attrs["input.value"]))
                self.assertIn("message", json.loads(attrs["output.value"]))

    def test_provider_failure_keeps_status_not_error_text(self):
        spans, raw = self.run_agent(model="broken-model")
        for name in ["agent.query", "step", "complete"]:
            span, = [s for s in spans if s.name == name]
            self.assertEqual(span.status.code, 2)
        self.assertNotIn(MARKER.encode(), raw)
        # Failed responses do not manufacture model usage or zero-token totals.
        llm, = [s for s in spans if s.name == "complete"]
        self.assertNotIn("llm.token_count.total", attributes(llm.attributes))

    def test_recoverable_tool_failure(self):
        spans, raw = self.run_agent(city="Atlantis")
        tool, = [s for s in spans if s.name == "tool.get_weather"]
        self.assertEqual(tool.status.code, 2)
        self.assertNotIn(MARKER.encode(), raw)

    def test_unmapped_metadata_and_links_are_removed(self):
        kv = lambda key, value: {"key": key, "value": {"stringValue": value}}
        with self.pipeline() as sink:
            payload = {"resourceSpans": [{
                "resource": {"attributes": [kv("secret.resource", MARKER)]},
                "scopeSpans": [{"scope": {"name": "swiftide-agent", "attributes": [kv("secret.scope", MARKER)]},
                                "spans": [{
                    "name": "complete", "traceId": "11" * 16, "spanId": "22" * 8,
                    "startTimeUnixNano": "1000000000", "endTimeUnixNano": "2000000000",
                    "traceState": "private=" + MARKER,
                    "attributes": [kv("langfuse.type", "GENERATION"), kv("input.value", MARKER)],
                    "status": {"code": 2, "message": MARKER},
                    "events": [{"name": MARKER, "timeUnixNano": "1500000000", "attributes": [
                        kv("langfuse.model", "fixture-model"), kv("langfuse.input", MARKER),
                        kv("langfuse.usage", '{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}')]}],
                }]}]}]}
            exported = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
            linked = dict(exported[0], spanId="55" * 8, name=MARKER,
                          links=[{"traceId": "33" * 16, "spanId": "44" * 8,
                                  "attributes": [kv("secret.link", MARKER)]}])
            exported.append(linked)
            req = urllib.request.Request("http://127.0.0.1:4318/v1/traces", json.dumps(payload).encode(),
                                         {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as response:
                self.assertEqual(response.status, 200)
            spans = self.wait_spans(sink, 1)
        self.assert_wire(sink)
        self.assertEqual(attributes(spans[0].attributes)["llm.token_count.total"], 5)
        self.assertNotIn(MARKER.encode(), b"".join(item[2] for item in sink.items))

    def test_collector_down_does_not_fail_the_agent(self):
        server = Server(Model)
        server.city = "Paris"
        try:
            result = subprocess.run([OPTIONS.binary, "What is the weather in Paris?"], timeout=30,
                                    env=model_env(server), capture_output=True, text=True)
        finally:
            server.close()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_build_has_no_langfuse_exporter(self):
        lock = (ROOT / "Cargo.lock").read_text()
        self.assertNotIn('name = "swiftide-langfuse"', lock)
        self.assertNotIn("LangfuseLayer", (ROOT / "src" / "main.rs").read_text())

    def test_page_code_matches_example(self):
        page = (ROOT.parents[2] / "src/pages/docs/integrations/frameworks/swiftide.mdx").read_text()
        files = {"yaml": (ROOT / "collector.yaml").read_text(),
                 "rust": (ROOT / "src" / "main.rs").read_text(),
                 "toml": (ROOT / "Cargo.toml").read_text()}
        checked = 0
        for language, source in files.items():
            for block in re.findall(r"```" + language + r"[^\n]*\n(.*?)```", page, re.S):
                for line in block.splitlines():
                    if line.strip():
                        self.assertIn(line, source, f"{language} page line missing from example")
                        checked += 1
        self.assertGreater(checked, 40)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", required=True)
    parser.add_argument("--binary", required=True)
    OPTIONS, remaining = parser.parse_known_args()
    # Do not accidentally send fixture data to someone else's local Collector.
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 4318)) == 0:
            raise SystemExit("127.0.0.1:4318 is already in use")
    unittest.main(argv=[__file__, *remaining], verbosity=2)
