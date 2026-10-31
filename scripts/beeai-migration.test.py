"""Run the published BeeAI example against a localhost OTLP receiver.

Install the versions in the guide and run this script with outbound network
blocked except localhost. No model API or Future AGI credentials are used.
"""
import contextlib
import io
import os
from pathlib import Path
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

PAGE = Path(__file__).resolve().parents[1] / "src/pages/docs/integrations/frameworks/beeai.mdx"


class BeeAIMigrationTest(unittest.TestCase):
    def test_published_example_exports_one_private_tool_span(self):
        payloads = []

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                payloads.append((self.path, dict(self.headers),
                                 self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *unused):
                pass

        server = HTTPServer(("127.0.0.1", 0), Receiver)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        blocks = re.findall(r"```python\n(.*?)\n```", PAGE.read_text(), re.S)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("traceai_beeai", blocks[0])
        environment = {
            "FI_BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "FI_API_KEY": "synthetic-api",
            "FI_SECRET_KEY": "synthetic-secret",
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        }
        try:
            with patch.dict(os.environ, environment, clear=True), contextlib.redirect_stdout(io.StringIO()):
                exec(compile(blocks[0], str(PAGE), "exec"), {"__name__": "__main__"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(len(payloads), 1)
        path, headers, body = payloads[0]
        self.assertEqual(path, "/tracer/v1/traces")
        lower_headers = {key.lower(): value for key, value in headers.items()}
        self.assertEqual(lower_headers["x-api-key"], "synthetic-api")
        self.assertEqual(lower_headers["x-secret-key"], "synthetic-secret")
        request = ExportTraceServiceRequest.FromString(body)
        spans = []
        for resource in request.resource_spans:
            attrs = {a.key: a.value.string_value for a in resource.resource.attributes}
            self.assertEqual(attrs["project_name"], "beeai-agent")
            self.assertEqual(attrs["project_type"], "observe")
            self.assertEqual(attrs["semantic_convention"], "openinference")
            spans.extend(span for scope in resource.scope_spans for span in scope.spans)
        self.assertEqual(len(spans), 1, "The replacement must not duplicate tool spans")
        span = spans[0]
        self.assertEqual(span.name, "shipping_days")
        attrs = {a.key: a.value.string_value for a in span.attributes}
        self.assertEqual(attrs["openinference.span.kind"], "TOOL")
        self.assertEqual(attrs["session.id"], "shipping-session")
        self.assertEqual(attrs["user.id"], "example-user")
        self.assertNotIn(b"domestic", body)
        self.assertNotIn(b"3 business days", body)


if __name__ == "__main__":
    unittest.main()
