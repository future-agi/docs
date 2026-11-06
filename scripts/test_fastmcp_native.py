"""Execute the page's exact snippets with published FastMCP and a loopback OTLP receiver.

Install fastmcp, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http and
pytest first. Run with outbound networking denied except localhost.
"""

import gzip
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
import pytest

PAGE = Path(__file__).resolve().parents[1] / "src/pages/docs/integrations/frameworks/fastmcp.mdx"
# -I prevents ambient Python imports; only our extracted, authored examples are added.
LOADER = "import sys,runpy; sys.path.insert(0,sys.argv[1]); runpy.run_path(sys.argv[2],run_name='__main__')"


def attrs(items):
    return {item.key: getattr(item.value, item.value.WhichOneof("value")) for item in items}


@pytest.fixture
def example(tmp_path):
    blocks = re.findall(r"```python\n# (\w+\.py)\n(.*?)\n```", PAGE.read_text(), re.S)
    assert {name for name, _ in blocks} == {"tracing.py", "server.py", "client.py"}
    for name, code in blocks:
        (tmp_path / name).write_text(code)
    (tmp_path / "home").mkdir()
    return tmp_path


@pytest.fixture
def receiver():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = self.rfile.read(int(self.headers["Content-Length"]))
            compressed = self.headers.get("Content-Encoding") == "gzip"
            if compressed:
                data = gzip.decompress(data)
            payload = ExportTraceServiceRequest.FromString(data)
            received.append((self.path, dict(self.headers), compressed, payload))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/tracer/v1/traces", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def environment(example, receiver, compression):
    return {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
        "HOME": str(example / "home"),
        "FI_API_KEY": "synthetic-fastmcp-api",
        "FI_SECRET_KEY": "synthetic-fastmcp-secret",
        "FI_PROJECT_NAME": "fastmcp-calculator",
        "FASTMCP_TELEMETRY_MODE": "native",
        "FASTMCP_CHECK_FOR_UPDATES": "off",
        "FI_HIDE_INPUTS": "true",
        "FI_HIDE_OUTPUTS": "true",
        "FI_HIDE_ERROR_DETAILS": "true",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": receiver[0],
        "OTEL_EXPORTER_OTLP_TRACES_COMPRESSION": compression,
        "OTEL_BSP_SCHEDULE_DELAY": "60000",
    }


def command(example, name):
    return [sys.executable, "-I", "-c", LOADER, str(example), str(example / name)]


def run(example, name, env):
    result = subprocess.run(command(example, name), cwd=example, env=env,
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    return result.stdout


def exported(receiver, compression):
    assert receiver[1], "no OTLP export reached the receiver"
    spans = []
    for path, headers, compressed, payload in receiver[1]:
        headers = {key.lower(): value for key, value in headers.items()}
        assert path == "/tracer/v1/traces"
        assert headers["content-type"] == "application/x-protobuf"
        assert headers["x-api-key"] == "synthetic-fastmcp-api"
        assert headers["x-secret-key"] == "synthetic-fastmcp-secret"
        assert compressed == (compression == "gzip")
        for resource in payload.resource_spans:
            resource_attrs = attrs(resource.resource.attributes)
            assert resource_attrs["project_name"] == "fastmcp-calculator"
            assert resource_attrs["project_type"] == "observe"
            for scope in resource.scope_spans:
                for span in scope.spans:
                    assert span.end_time_unix_nano >= span.start_time_unix_nano
                    # Export credentials belong only in HTTP headers, never span data.
                    assert b"synthetic-fastmcp" not in span.SerializeToString()
                    spans.append((scope.scope.name, span))
    assert len({span.span_id for _, span in spans}) == len(spans)
    return spans


def assert_tool_ancestry(spans, tool="add"):
    native = [span for scope, span in spans
              if scope == "fastmcp" and attrs(span.attributes).get("gen_ai.tool.name") == tool]
    server = [span for span in native if span.kind == 2]  # OTLP SERVER
    client = [span for span in native if span.kind == 3]  # OTLP CLIENT
    assert len(server) == len(client) == 1, "one native execution and one logical call"
    assert server[0].trace_id == client[0].trace_id
    by_id = {span.span_id: span for _, span in spans}
    parent = server[0]
    visited = set()
    while parent.span_id != client[0].span_id:
        assert parent.span_id not in visited, "cycle in exported parent chain"
        visited.add(parent.span_id)
        parent = by_id[parent.parent_span_id]
    assert attrs(server[0].attributes)["mcp.method.name"] == "tools/call"
    return server[0], client[0]


@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_exact_http_snippets(example, receiver, compression):
    env = environment(example, receiver, compression)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        env["MCP_PORT"] = str(reserved.getsockname()[1])
    process = subprocess.Popen(command(example, "server.py"), cwd=example, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with socket.create_connection(("127.0.0.1", int(env["MCP_PORT"])), timeout=0.2):
                    break
            except OSError:
                assert process.poll() is None, process.communicate()[1]
                assert time.monotonic() < deadline, "server did not become ready"
                threading.Event().wait(0.05)
        assert run(example, "client.py", env).strip() == "5"
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            _, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            pytest.fail("server did not shut down cleanly")
    assert process.returncode == 0, stderr
    assert_tool_ancestry(exported(receiver, compression))


@pytest.mark.parametrize("transport", ["inprocess", "stdio"])
@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_native_transport_and_privacy(example, receiver, transport, compression):
    env = environment(example, receiver, compression)
    # Test-only operations expose whether normal content and errors enter telemetry.
    (example / "operations.py").write_text('''from server import server
@server.tool
def echo(value: str) -> str:
    return value
@server.tool
def fail() -> str:
    raise ValueError("synthetic-error-detail")
''')
    (example / "stdio_server.py").write_text('''from tracing import provider
from operations import server
try:
    server.run(transport="stdio", show_banner=False)
finally:
    provider.shutdown()
''')
    if transport == "inprocess":
        target = "from operations import server\ntarget = server"
    else:
        target = f'''import os, sys
from fastmcp.client.transports import StdioTransport
target = StdioTransport(command=sys.executable, args={command(example, "stdio_server.py")[1:]!r}, env=dict(os.environ))'''
    (example / "probe.py").write_text('''import asyncio
from tracing import provider
from fastmcp import Client
from fastmcp.exceptions import ToolError
''' + target + '''
async def main():
    async with Client(target) as client:
        assert (await client.call_tool("add", {"a": 2, "b": 3})).data == 5
        assert (await client.call_tool("echo", {"value": "synthetic-normal-content"})).data == "synthetic-normal-content"
        try:
            await client.call_tool("fail", {})
        except ToolError:
            pass
        else:
            raise AssertionError("tool error was swallowed")
try:
    asyncio.run(main())
finally:
    provider.shutdown()
''')
    run(example, "probe.py", env)
    spans = exported(receiver, compression)
    assert_tool_ancestry(spans)
    assert_tool_ancestry(spans, "echo")
    errors = assert_tool_ancestry(spans, "fail")
    assert all(span.status.code == 2 for span in errors)
    assert not any(b"synthetic-normal-content" in span.SerializeToString() for _, span in spans)
    # Pin the warning: native errors are NOT sanitized by traceAI hide flags.
    assert any(b"synthetic-error-detail" in span.SerializeToString() for _, span in spans)
