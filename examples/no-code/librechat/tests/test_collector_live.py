"""Contract test: run the shipped collector config in Docker and feed it what LibreChat v0.8.8 really sent.

The fixtures were recorded from a LibreChat v0.8.8 container (see README): tests/fixtures/langfuse-export-v0.8.8.json
is the agent-run export (three turns: a tool call, a failing tool, a provider failure) and
tests/fixtures/backend-export-v0.8.8.json a sample of the backend export. A small HTTP sink stands in for
Future AGI and records what the collector forwards. Skipped when Docker or the collector image is missing.
"""
import base64
import http.server
import json
import os
import pathlib
import secrets
import socket
import subprocess
import threading
import time
import urllib.request

import pytest

try:
    from google.protobuf.json_format import MessageToDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
except ImportError:  # pragma: no cover
    pytest.skip("opentelemetry-proto is not installed", allow_module_level=True)

HERE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = HERE / "tests" / "fixtures"
IMAGE = f"otel/opentelemetry-collector-contrib:{os.environ.get('OTELCOL_VERSION', '0.162.0')}"
PREFIX = os.environ.get("CONTAINER_PREFIX", "librechat-fi-contract")
BASIC = "Basic " + base64.b64encode(b"test-api-key:test-secret-key").decode()


def _docker_ok():
    try:
        out = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
        return out.returncode == 0
    except FileNotFoundError:
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason=f"docker or {IMAGE} not available")


class Sink(http.server.BaseHTTPRequestHandler):
    received = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Sink.received.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                              "body": body})
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.end_headers()
        self.wfile.write(b"")

    def log_message(self, *args):
        pass


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def sink():
    port = _free_port()
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), Sink)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield port
    server.shutdown()


def _start_collector(sink_port, capture):
    name = f"{PREFIX}-{secrets.token_hex(3)}"
    lf, be = _free_port(), _free_port()
    cmd = ["docker", "run", "-d", "--rm", "--name", name, "--memory", "128m",
           "--add-host", "host.docker.internal:host-gateway",
           "-p", f"127.0.0.1:{lf}:4319", "-p", f"127.0.0.1:{be}:4318",
           "-e", f"FI_TRACES_URL=http://host.docker.internal:{sink_port}/v1/traces",
           "-e", "FI_PROJECT_NAME=contract-project", "-e", f"FI_CAPTURE_CONTENT={'true' if capture else 'false'}",
           "-v", f"{HERE / 'otelcol' / 'otelcol.yaml'}:/etc/otelcol/config.yaml:ro",
           IMAGE, "--config=/etc/otelcol/config.yaml"]
    subprocess.run(cmd, check=True, capture_output=True)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{be}/v1/traces", timeout=1)
        except urllib.error.HTTPError:
            break  # the receiver answers (405 for GET): it is up
        except OSError:
            time.sleep(0.5)
    return name, lf, be


def _post(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200


def _collect(n_before, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(Sink.received) > n_before:
            time.sleep(3)  # the collector batches for up to 2 s; let the rest arrive
            return Sink.received[n_before:]
        time.sleep(0.5)
    raise AssertionError("collector forwarded nothing")


def _spans(requests):
    out = []
    for r in requests:
        msg = ExportTraceServiceRequest()
        msg.ParseFromString(r["body"])
        for rs in MessageToDict(msg)["resourceSpans"]:
            res = {a["key"]: a["value"] for a in rs["resource"].get("attributes", [])}
            for ss in rs["scopeSpans"]:
                for sp in ss["spans"]:
                    attrs = {a["key"]: next(iter(a["value"].values()), None) for a in sp.get("attributes", [])}
                    out.append({"name": sp["name"], "attrs": attrs, "status": sp.get("status", {}),
                                "resource": res, "events": sp.get("events", []), "kind": sp.get("kind")})
    return out


def _run(sink_port, capture, payload, receiver, headers):
    """Start the collector, post one OTLP/JSON payload to a receiver, return what reached the sink."""
    name, lf, be = _start_collector(sink_port, capture)
    try:
        n = len(Sink.received)
        url = (f"http://127.0.0.1:{lf}/api/public/otel/v1/traces" if receiver == "langfuse"
               else f"http://127.0.0.1:{be}/v1/traces")
        _post(url, payload, headers)
        return _collect(n)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _fixture(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def langfuse_off(sink):
    return _run(sink, False, _fixture("langfuse-export-v0.8.8.json"), "langfuse", {"Authorization": BASIC})


@pytest.fixture(scope="module")
def langfuse_on(sink):
    return _run(sink, True, _fixture("langfuse-export-v0.8.8.json"), "langfuse", {"Authorization": BASIC})


@pytest.fixture(scope="module")
def backend(sink):
    payload = _fixture("backend-export-v0.8.8.json")
    # A deployment that forgot OTEL_NODE_RESOURCE_DETECTORS=env: the collector must still drop these.
    payload["resourceSpans"][0]["resource"]["attributes"] += [
        {"key": "host.name", "value": {"stringValue": "build-box-7"}},
        {"key": "process.owner", "value": {"stringValue": "alice"}},
        {"key": "process.command_args",
         "value": {"arrayValue": {"values": [{"stringValue": "/home/alice/app.js"}]}}},
    ]
    return _run(sink, False, payload, "backend", {"X-Api-Key": "test-api-key", "X-Secret-Key": "test-secret-key"})


# ---- transport -------------------------------------------------------------------------------------------

def test_forwards_uncompressed_protobuf_to_traces_path(langfuse_off):
    for r in langfuse_off:
        assert r["path"] == "/v1/traces"
        assert r["headers"].get("content-type") == "application/x-protobuf"
        assert "gzip" not in r["headers"].get("content-encoding", "")
        gzip_magic = b"\x1f\x8b"
        assert not r["body"].startswith(gzip_magic)


def test_passes_langfuse_basic_auth_through(langfuse_off):
    assert all(r["headers"].get("authorization") == BASIC for r in langfuse_off)
    assert not any("x-api-key" in r["headers"] or "x-secret-key" in r["headers"] for r in langfuse_off)


def test_passes_backend_key_headers_through(backend):
    for r in backend:
        assert r["headers"].get("x-api-key") == "test-api-key"
        assert r["headers"].get("x-secret-key") == "test-secret-key"
        assert "authorization" not in r["headers"]


def test_sets_project_on_every_resource(langfuse_off, backend):
    for s in _spans(langfuse_off) + _spans(backend):
        assert s["resource"]["project_name"] == {"stringValue": "contract-project"}
        assert s["resource"]["project_type"] == {"stringValue": "observe"}


# ---- agent-run mapping -----------------------------------------------------------------------------------

def test_maps_span_kinds(langfuse_off):
    spans = _spans(langfuse_off)
    kinds = {s["name"]: s["attrs"].get("fi.span.kind") for s in spans}
    assert kinds["llm"] == "LLM"
    assert kinds["agent"] == "AGENT"
    assert kinds["AgentGraph"] == "AGENT"
    assert kinds["tool-dispatch"] == "TOOL"
    assert all(s["attrs"].get("fi.span.kind") for s in spans)


def test_maps_model_tokens_and_provider(langfuse_off):
    llm = [s for s in _spans(langfuse_off) if s["name"] == "llm" and s["status"].get("code") != "STATUS_CODE_ERROR"]
    assert llm
    for s in llm:
        assert s["attrs"]["gen_ai.request.model"] == "gpt-6-luna"
        assert s["attrs"]["llm.model_name"] == "gpt-6-luna"
        assert s["attrs"]["gen_ai.system"] == "openai"
        assert int(s["attrs"]["gen_ai.usage.input_tokens"]) > 0
        assert int(s["attrs"]["gen_ai.usage.output_tokens"]) > 0
        assert int(s["attrs"]["llm.token_count.total"]) > 0


def test_names_the_tool(langfuse_off):
    tools = {s["attrs"].get("tool.name") for s in _spans(langfuse_off) if s["name"] == "tool-dispatch"}
    assert tools == {"get_order_status_mcp_order-tools", "cancel_order_mcp_order-tools"}


def test_keeps_session_and_user(langfuse_off):
    for s in _spans(langfuse_off):
        assert s["attrs"].get("session.id")
        assert s["attrs"].get("user.id")


def test_provider_failure_is_error_without_text_by_default(langfuse_off):
    errors = [s for s in _spans(langfuse_off) if s["status"].get("code") == "STATUS_CODE_ERROR"]
    assert {s["name"] for s in errors} >= {"llm", "agent", "AgentGraph"}
    assert all(s["status"].get("message") == "error" for s in errors)


# ---- privacy -------------------------------------------------------------------------------------------

CONTENT = ["FIXTURE-MARKER", "F-1001", "F-1002", "DemoPost", "cancellation service unavailable",
           "unknown provider for model", "shipped"]


def test_content_off_removes_prompts_replies_tool_io_and_error_text(langfuse_off):
    blob = b"".join(r["body"] for r in langfuse_off)
    for needle in CONTENT:
        assert needle.encode() not in blob, needle
    for s in _spans(langfuse_off):
        assert not any(k.startswith(("input.", "output.")) for k in s["attrs"])
        assert "langfuse.observation.input" not in s["attrs"]
        assert "langfuse.observation.output" not in s["attrs"]
        assert "langfuse.observation.status_message" not in s["attrs"]


def test_content_on_fills_input_output_and_error_text(langfuse_on):
    spans = _spans(langfuse_on)
    blob = b"".join(r["body"] for r in langfuse_on)
    assert b"FIXTURE-MARKER-1" in blob and b"DemoPost" in blob
    llm = [s for s in spans if s["name"] == "llm" and s["status"].get("code") != "STATUS_CODE_ERROR"]
    assert all("FIXTURE-MARKER" in s["attrs"]["input.value"] for s in llm)
    assert all(s["attrs"].get("output.value") for s in llm)
    failed = [s for s in spans if s["name"] == "llm" and s["status"].get("code") == "STATUS_CODE_ERROR"]
    assert failed and "unknown provider for model" in failed[0]["status"]["message"]


def test_backend_drops_client_and_host_identifiers(backend):
    spans = _spans(backend)
    banned_attrs = ("net.peer.ip", "network.peer.address", "network.peer.port", "http.user_agent",
                    "user_agent.original", "http.host", "net.host.name", "net.host.ip", "net.host.port")
    for s in spans:
        for key in banned_attrs:
            assert key not in s["attrs"], (s["name"], key)
        assert not any(k.startswith(("host.", "process.", "os.", "container.")) for k in s["resource"])
    blob = b"".join(r["body"] for r in backend)
    for needle in (b"build-box-7", b"alice", b"Mozilla/5.0"):
        assert needle not in blob
    server = [s for s in spans if s["name"] == "POST /api/agents/chat/:endpoint"]
    assert server and server[0]["attrs"].get("user.id") == server[0]["attrs"].get("enduser.id")


def test_backend_keeps_outgoing_destination(backend):
    client = [s for s in _spans(backend) if s["name"] == "POST"]
    assert client and client[0]["attrs"].get("server.address")


def test_backend_drops_parentless_background_database_spans_only(backend):
    names = [s["name"] for s in _spans(backend)]
    assert "mongoose.AgentTriggerDelivery.find" not in names
    assert "mongoose.User.findOne" in names  # a request's database call stays
    assert "librechat.sse.stream" in names
