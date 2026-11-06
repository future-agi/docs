"""Execute the published MCP snippets against a loopback OTLP receiver.

Install the page's Python dependencies, then run this file with Python.
No model, cloud service, application credentials, or traceAI package is used.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

PAGE = Path(__file__).resolve().parents[1] / "src/pages/docs/integrations/traceai/mcp-python.mdx"


def attributes(entries):
    return {entry["key"]: next(iter(entry["value"].values())) for entry in entries}


class NativeMCPGuideTest(unittest.TestCase):
    def run_guide(self, *, concurrent=False, failure=False):
        page = PAGE.read_text()
        snippets = dict(re.findall(r'```python title="([^"]+)"\n(.*?)\n```', page, re.S))
        self.assertEqual(set(snippets), {"telemetry.py", "server.py", "client.py"})
        self.assertNotIn("traceai_mcp", "".join(snippets.values()))
        self.assertIn("https://api.futureagi.com/tracer/v1/traces", page)
        self.assertIn("FI_HIDE_ERROR_DETAILS", page)
        self.assertIn("do not control native MCP telemetry", page)
        if concurrent:
            snippets["client.py"] = snippets["client.py"].replace(
                'result = await session.call_tool("add", {"a": 2, "b": 3})',
                'results = await asyncio.gather(*(session.call_tool("add", {"a": n, "b": 3}) for n in range(4)))\n'
                '            assert [r.content[0].text for r in results] == ["3", "4", "5", "6"]\n'
                '            result = results[2]',
            )
        if failure:
            snippets["server.py"] = snippets["server.py"].replace(
                "return a + b", 'raise ValueError("public-tool-failure")'
            )
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/tracer/v1/traces":
                    self.send_error(404)
                    return
                message = ExportTraceServiceRequest()
                message.ParseFromString(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((dict(self.headers), MessageToDict(message)))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as receiver:
            thread = Thread(target=receiver.serve_forever, daemon=True)
            thread.start()
            try:
                with tempfile.TemporaryDirectory(prefix="mcp-native-guide-") as tmp:
                    for name, source in snippets.items():
                        Path(tmp, name).write_text(source)
                    env = {
                        "PATH": os.defpath,
                        "HOME": tmp,
                        "FI_API_KEY": "synthetic-api-key",
                        "FI_SECRET_KEY": "synthetic-secret-key",
                        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT":
                            f"http://127.0.0.1:{receiver.server_port}/tracer/v1/traces",
                    }
                    run = subprocess.run(
                        [sys.executable, str(Path(tmp, "client.py"))],
                        cwd=tmp, env=env, capture_output=True, text=True, timeout=45,
                    )
                    self.assertEqual(run.returncode, 0, run.stderr)
                    if failure:
                        self.assertEqual(run.stdout.strip(), "Error executing tool add")
                    else:
                        self.assertEqual(run.stdout.strip(), "5")
            finally:
                receiver.shutdown()
                thread.join()

        self.assertTrue(requests, "shutdown must deliver spans from both processes")
        spans = []
        for headers, payload in requests:
            headers = {key.lower(): value for key, value in headers.items()}
            self.assertEqual(headers["x-api-key"], "synthetic-api-key")
            self.assertEqual(headers["x-secret-key"], "synthetic-secret-key")
            for group in payload["resourceSpans"]:
                resource = attributes(group["resource"]["attributes"])
                self.assertEqual(resource["project_name"], "mcp_project")
                self.assertEqual(resource["project_type"], "observe")
                self.assertEqual(resource["service.name"], "mcp-example")
                for scope in group["scopeSpans"]:
                    self.assertEqual(scope["scope"]["name"], "mcp-python-sdk")
                    spans.extend(scope["spans"])

        tools = [s for s in spans if attributes(s.get("attributes", []))
                 .get("mcp.method.name") == "tools/call"]
        clients = [s for s in tools if s["kind"] == "SPAN_KIND_CLIENT"]
        servers = [s for s in tools if s["kind"] == "SPAN_KIND_SERVER"]
        expected = 4 if concurrent else 1
        self.assertEqual(len(clients), expected, tools)
        self.assertEqual(len(servers), expected, tools)
        self.assertEqual(len({s["spanId"] for s in tools}), expected * 2)
        for server in servers:
            parent = next(s for s in clients if s["spanId"] == server["parentSpanId"])
            self.assertEqual(server["traceId"], parent["traceId"])
            self.assertNotEqual(int.from_bytes(base64.b64decode(server["traceId"]), "big"), 0)
            attrs = attributes(server["attributes"])
            self.assertEqual(attrs["gen_ai.operation.name"], "execute_tool")
            self.assertEqual(attrs["gen_ai.tool.name"], "add")
            self.assertEqual(server["name"], "tools/call add")
            for key in ("input.value", "output.value", "gen_ai.tool.call.arguments", "gen_ai.tool.call.result"):
                self.assertNotIn(key, attrs)
            if failure:
                self.assertEqual(server["status"]["code"], "STATUS_CODE_ERROR")
            else:
                self.assertNotEqual(server.get("status", {}).get("code"), "STATUS_CODE_ERROR")
        return len(spans)

    def test_exact_customer_snippets(self):
        self.run_guide()

    def test_concurrent_requests_have_one_client_server_pair_each(self):
        self.run_guide(concurrent=True)

    def test_tool_failure_sets_native_server_error(self):
        self.run_guide(failure=True)


if __name__ == "__main__":
    unittest.main()
