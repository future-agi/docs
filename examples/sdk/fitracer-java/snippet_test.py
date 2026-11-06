"""Compile the page's Java snippets against Maven Central and inspect exported OTLP.

Run: python -I snippet_test.py
CI separates --compile-only (dependency downloads) from --run-only (loopback only).
Application services are synthetic fixtures; no tracing implementation is replaced.
"""

import argparse
import gzip
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import unittest

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "target"
PAGE = ROOT.parents[2] / "src/pages/docs/sdk/tracing/fitracer.mdx"


def compile_snippets():
    tab = PAGE.read_text().split('<Tab title="Java">')[1].split('</Tab>')[0]
    blocks = [re.sub(r"^    ", "", block, flags=re.M)
              for block in re.findall(r"```java\n(.*?)```", tab, re.S)]
    if len(blocks) != 2:
        raise AssertionError("Expected both lambda and manual Java examples")
    imports = sorted(set(re.findall(r"^import .+;", "\n".join(blocks), re.M)))
    bodies = [re.sub(r"^import .+;\n", "", block, flags=re.M) for block in blocks]
    # Keep the documented operations unchanged. Supply only application context
    # and deterministic services in place of external vector/LLM/tool calls.
    source = "\n".join(imports) + """
public class GuideExample {
    static class VectorDb { String search(String question) { return "synthetic document"; } }
    static class Llm {
        String generate(String question, String docs) { return "synthetic answer"; }
    }
    static String executeTool(String input) { return "synthetic tool output"; }
    static void manual(ai.traceai.FITracer tracer) {
        String inputJson = "synthetic tool input";
""" + bodies[1] + """
    }
    public static void main(String[] args) {
        ai.traceai.TraceAI.initFromEnvironment();
        try {
            String question = "What is Python?";
            VectorDb vectorDb = new VectorDb();
            Llm llm = new Llm();
""" + bodies[0] + """
            if (!"synthetic answer".equals(result)) throw new AssertionError(result);
            if (io.opentelemetry.api.trace.Span.current().getSpanContext().isValid())
                throw new AssertionError("Callback scope leaked after trace returned");
            manual(tracer);
        } finally {
            ai.traceai.TraceAI.shutdown();
        }
    }
}
"""
    directory = TARGET / "snippet-source"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "GuideExample.java").write_text(source)
    subprocess.run([
        "mvn", "-B", "-f", str(ROOT / "pom.xml"), "compile",
        "dependency:build-classpath", "-Dmdep.outputFile=target/classpath.txt",
    ], check=True, timeout=300)


class JavaSnippetTest(unittest.TestCase):
    def test_exported_spans(self):
        requests = []

        class Collector(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    chunks = []
                    while True:
                        size = int(self.rfile.readline().split(b";", 1)[0], 16)
                        if size == 0:
                            while self.rfile.readline().strip():
                                pass
                            break
                        chunks.append(self.rfile.read(size))
                        self.rfile.read(2)
                    body = b"".join(chunks)
                else:
                    body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                requests.append((self.path, self.headers, ExportTraceServiceRequest.FromString(body)))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", "0")
                self.end_headers()

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # Never consume ambient credentials, endpoints, or privacy settings.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("FI_", "OTEL_"))}
        env.update(FI_BASE_URL=f"http://127.0.0.1:{server.server_port}",
                   FI_API_KEY="synthetic-api-key", FI_SECRET_KEY="synthetic-secret-key",
                   FI_PROJECT_NAME="my-project")
        try:
            classpath = str(TARGET / "classes") + os.pathsep + (TARGET / "classpath.txt").read_text().strip()
            subprocess.run(["java", "-cp", classpath, "GuideExample"], env=env,
                           check=True, timeout=60)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        def attrs(entries):
            return {entry.key: getattr(entry.value, entry.value.WhichOneof("value"))
                    for entry in entries}

        spans = []
        self.assertTrue(requests, "Published exporter must send OTLP before shutdown returns")
        for path, headers, request in requests:
            self.assertEqual(path, "/tracer/v1/traces")
            self.assertEqual(headers["X-Api-Key"], "synthetic-api-key")
            self.assertEqual(headers["X-Secret-Key"], "synthetic-secret-key")
            self.assertEqual(headers["Content-Type"], "application/x-protobuf")
            for resource in request.resource_spans:
                self.assertEqual(attrs(resource.resource.attributes)["project_name"], "my-project")
                for scope in resource.scope_spans:
                    spans.extend(scope.spans)
        self.assertCountEqual([span.name for span in spans],
                              ["rag-pipeline", "retrieve", "generate", "tool-call"])
        by_name = {span.name: span for span in spans}
        parent = by_name["rag-pipeline"]
        self.assertFalse(parent.parent_span_id)
        for name, kind in [("rag-pipeline", "CHAIN"), ("retrieve", "RETRIEVER"),
                           ("generate", "LLM"), ("tool-call", "TOOL")]:
            span = by_name[name]
            self.assertEqual(attrs(span.attributes)["gen_ai.span.kind"], kind.lower())
            self.assertEqual(attrs(span.attributes)["fi.span.kind"], kind)
            self.assertEqual(span.status.code, 1, name)
            self.assertGreaterEqual(span.end_time_unix_nano, span.start_time_unix_nano)
            self.assertGreater(span.start_time_unix_nano, 0)
        for name in ("retrieve", "generate"):
            self.assertEqual(by_name[name].trace_id, parent.trace_id)
            self.assertEqual(by_name[name].parent_span_id, parent.span_id)
        self.assertFalse(by_name["tool-call"].parent_span_id)
        self.assertNotEqual(by_name["tool-call"].trace_id, parent.trace_id)
        self.assertEqual(attrs(parent.attributes)["input.value"], "What is Python?")
        self.assertEqual(attrs(parent.attributes)["output.value"], "synthetic answer")
        self.assertEqual(attrs(by_name["retrieve"].attributes)["input.value"], "What is Python?")
        self.assertEqual(attrs(by_name["retrieve"].attributes)["output.value"], "synthetic document")
        generated = attrs(by_name["generate"].attributes)
        self.assertEqual(json.loads(generated["gen_ai.input.messages"]), [
            {"role": "system", "content": "Answer using the context."},
            {"role": "user", "content": "What is Python?"},
        ])
        self.assertEqual(json.loads(generated["gen_ai.output.messages"]), [
            {"role": "assistant", "content": "synthetic answer"},
        ])
        self.assertEqual(generated["gen_ai.usage.input_tokens"], 50)
        self.assertEqual(generated["gen_ai.usage.output_tokens"], 200)
        self.assertEqual(attrs(by_name["tool-call"].attributes)["output.value"], "synthetic tool output")
        print("Published Java SDK exported retrieve, generate, rag-pipeline, tool-call with correct parentage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--compile-only", action="store_true")
    mode.add_argument("--run-only", action="store_true")
    args = parser.parse_args()
    if not args.run_only:
        compile_snippets()
    if not args.compile_only:
        unittest.main(argv=[__file__], verbosity=2)
