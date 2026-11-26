"""Real application/SDK contract over loopback HTTP; synthetic model and OTLP peers.

No AWS deployment or Future AGI backend/UI claim is made by these tests.
"""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
import pytest

HERE = Path(__file__).resolve().parents[1]
PAGE = HERE.parents[2] / "src/pages/docs/integrations/traceai/bedrock-agentcore.mdx"
CONTENT = "SYNTHETIC_CONTENT_1021"
ERROR = "/home/synthetic-user/private-order.txt on synthetic-host; key=synthetic-error-secret"
SESSION = "synthetic-session-00000000000000000001"


def _value(value):
    for key, item in value.items():
        if key == "array_value":
            return [_value(v) for v in item.get("values", [])]
        if key == "kvlist_value":
            return _attrs(item.get("values", []))
        return item


def _attrs(values):
    return {v["key"]: _value(v["value"]) for v in values}


def _spans(batches):
    result = []
    for batch in batches:
        for rs in batch["request"].get("resource_spans", []):
            for scope in rs.get("scope_spans", []):
                for span in scope.get("spans", []):
                    result.append({**span, "attributes": _attrs(span.get("attributes", [])),
                                   "resource": _attrs(rs.get("resource", {}).get("attributes", []))})
    return result


@pytest.fixture
def peers():
    batches, calls = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.endswith("/chat/completions"):
                payload = json.loads(raw)
                calls.append(payload)
                if "FAIL-PRIVACY" in json.dumps(payload["messages"]):
                    self.respond(400, json.dumps({"error": {"message": ERROR,
                        "type": "invalid_request_error", "code": "bad_model"}}).encode(), "application/json")
                    return
                has_tool = any(m["role"] == "tool" for m in payload["messages"])
                order = CONTENT if CONTENT in json.dumps(payload["messages"]) else "A-100"
                message = {"role": "assistant", "content": f"Order {order} has shipped." if has_tool else None}
                if not has_tool:
                    message["tool_calls"] = [{"id": "call_synthetic_1", "type": "function", "function": {
                        "name": "lookup_order", "arguments": json.dumps({"order_id": order})}}]
                usage = {"prompt_tokens": 24, "completion_tokens": 9, "total_tokens": 33}
                base = {"id": "chatcmpl-synthetic", "created": 1700000000, "model": "gpt-4o-mini"}
                finish = "stop" if has_tool else "tool_calls"
                if not payload.get("stream"):
                    body = {**base, "object": "chat.completion", "choices": [
                        {"index": 0, "message": message, "finish_reason": finish}], "usage": usage}
                    self.respond(200, json.dumps(body).encode(), "application/json")
                else:
                    delta = dict(message)
                    if "tool_calls" in delta:
                        delta["tool_calls"] = [{"index": 0, **delta["tool_calls"][0]}]
                    chunks = [
                        {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                        {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
                        {**base, "object": "chat.completion.chunk", "choices": [], "usage": usage},
                    ]
                    body = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
                    self.respond(200, body.encode(), "text/event-stream")
                return
            req = ExportTraceServiceRequest()
            req.ParseFromString(raw)
            batches.append({"path": self.path, "key": self.headers.get("X-Api-Key"),
                "secret": self.headers.get("X-Secret-Key"), "encoding": self.headers.get("Content-Encoding"),
                "request": MessageToDict(req, preserving_proto_field_name=True)})
            self.respond(200, b"", "application/x-protobuf")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", batches, calls
    finally:
        server.shutdown()
        server.server_close()


def _call(url, payload=None, headers=None):
    req = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _environment(origin, port, hidden, errors_hidden):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OTEL_", "OPENAI_", "AWS_"))}
    env.update(DISABLE_ADOT_OBSERVABILITY="true", FI_API_KEY="synthetic-api", FI_SECRET_KEY="synthetic-secret",
        FI_BASE_URL=origin, FI_PROJECT_NAME="agentcore-contract", OPENAI_API_KEY="synthetic-model",
        OPENAI_BASE_URL=origin + "/v1", AGENT_MODEL="gpt-4o-mini", PORT=str(port), AWS_EC2_METADATA_DISABLED="true",
        FI_HIDE_INPUTS=str(hidden).lower(), FI_HIDE_OUTPUTS=str(hidden).lower(),
        FI_HIDE_ERROR_DETAILS=str(errors_hidden).lower(),
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=origin + "/tracer/v1/traces", OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf",
        OTEL_EXPORTER_OTLP_HEADERS="X-Api-Key=synthetic-api,X-Secret-Key=synthetic-secret",
        OTEL_RESOURCE_ATTRIBUTES="project_name=agentcore-contract,project_type=observe", OTEL_SERVICE_NAME="order-agent",
        OTEL_BSP_SCHEDULE_DELAY="60000", OTEL_EXPORTER_OTLP_TIMEOUT="1",
        OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_latest_experimental,gen_ai_span_attributes_only" +
            (",gen_ai_unredacted_attributes=" if hidden else ""))
    return env


@pytest.mark.parametrize("variant,hidden,errors_hidden,failing", [
    ("langchain", True, True, False), ("langchain", False, True, False),
    ("langchain", True, True, True), ("langchain", False, True, True),
    ("langchain", False, False, True),  # negative control: error text is not inherently private
    ("strands", True, False, False), ("strands", False, False, False),
    ("strands", True, False, True),  # native content redaction does not hide exception details
])
def test_real_application_export(peers, tmp_path, variant, hidden, errors_hidden, failing):
    origin, batches, calls = peers
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    script = HERE / f"agent_{variant}.py"
    if variant == "langchain":
        # Execute the page's exact primary snippet, not a separately maintained facsimile.
        match = re.search(r'```python title="agent_langchain.py"\n(.*?)\n```', PAGE.read_text(), re.S)
        assert match and match.group(1) == script.read_text().rstrip()
        script = tmp_path / script.name
        script.write_text(match.group(1) + "\n")
    with (tmp_path / "app.log").open("w") as log:
        process = subprocess.Popen([sys.executable, str(script)], cwd=tmp_path,
            env=_environment(origin, port, hidden, errors_hidden), stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                assert process.poll() is None, (tmp_path / "app.log").read_text()
                try:
                    if _call(f"http://127.0.0.1:{port}/ping")[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.2)
            else:
                pytest.fail("application startup timed out")
            for i in range(1 if failing else 2):
                before = len(_spans(batches))
                status, response = _call(f"http://127.0.0.1:{port}/invocations",
                    {"prompt": "FAIL-PRIVACY" if failing else f"What is the status of order {CONTENT}?"},
                    {"X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": SESSION,
                     "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                     "baggage": "untrusted=synthetic-header-secret"})
                assert status == (500 if failing else 200), response
                assert len(_spans(batches)) > before, "force_flush must export before the response"
            flat = _spans(batches)
            (tmp_path / "export.json").write_text(json.dumps(flat, indent=2))
            roots = [s for s in flat if s["name"] == "agentcore.invocation"]
            assert len(roots) == (1 if failing else 2)
            assert all(not s.get("parent_span_id") for s in roots)
            assert len({s["trace_id"] for s in roots}) == len(roots)
            assert len({(s["trace_id"], s["span_id"]) for s in flat}) == len(flat), "duplicate exporter"
            assert all(s["attributes"].get("session.id") == SESSION for s in roots)
            if variant == "langchain":
                assert all(s["attributes"].get("session.id") == SESSION for s in flat)
            else:
                agent_spans = [s for s in flat if s["name"].startswith("invoke_agent")]
                assert agent_spans and all(s["attributes"].get("session.id") == SESSION for s in agent_spans)
            ids = {s["span_id"] for s in flat}
            assert all(s["parent_span_id"] in ids for s in flat if s.get("parent_span_id"))
            assert all(b["path"] == "/tracer/v1/traces" and b["key"] == "synthetic-api" and
                       b["secret"] == "synthetic-secret" and b["encoding"] is None for b in batches)
            assert all(s["resource"]["project_name"] == "agentcore-contract" for s in flat)
            dumped = json.dumps(flat)
            assert "synthetic-header-secret" not in dumped
            if failing:
                assert all(s.get("status", {}).get("code") == "STATUS_CODE_ERROR" for s in roots)
                assert (ERROR in dumped) is not (variant == "langchain" and errors_hidden)
                if variant == "langchain" and errors_hidden:
                    assert all(not s.get("status", {}).get("message") for s in flat)
                    assert "exception.stacktrace" not in dumped and "exception.message" not in dumped
                    assert "error.type" in dumped or "exception.type" in dumped
            else:
                assert (CONTENT in dumped) is not hidden
                assert any("lookup_order" in s["name"] for s in flat)
                assert any(any("token" in k for k in s["attributes"]) for s in flat)
                assert len(calls) >= 4
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def test_customer_route_contains_no_helper_or_qa_diary():
    page = PAGE.read_text()
    assert "How it was tested" not in page and "qualification is pending" not in page
    assert "Never exported" not in page and "wrapper stays harmless" not in page
    assert not (HERE / "agentcore_tracing.py").exists()
    for name in ["agent_langchain.py", "agent_strands.py"]:
        code = (HERE / name).read_text()
        assert "agentcore_tracing" not in code
        assert "class " not in code and "SpanExporter" not in code
    assert "exception messages or stack traces" in page


@pytest.mark.parametrize("mode", ["false", "raise"])
def test_failed_flush_preserves_result_and_error(tmp_path, mode):
    # Run the unmodified LangChain entrypoint with an in-process real traced chain.
    # Only the model and final exporter are replaced; no paid endpoint is called.
    probe = '''
import runpy, sys
from types import SimpleNamespace
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from starlette.testclient import TestClient
ns = runpy.run_path(sys.argv[1])
provider = ns['provider']
def flush(**kwargs):
    assert kwargs == {'timeout_millis': 5000}
    if sys.argv[2] == 'raise': raise RuntimeError('synthetic flush failure')
    return False
provider.force_flush = flush
def body(value):
    if value['messages'][0]['content'] == 'fail': raise ValueError('synthetic application failure')
    return {'messages': [AIMessage(content='ok')]}
ns['invoke'].__globals__['agent'] = RunnableLambda(body)
client = TestClient(ns['app'])
assert client.post('/invocations', json={'prompt': 'ok'}).status_code == 200
assert client.post('/invocations', json={'prompt': 'fail'}).status_code == 500
provider.shutdown()
'''
    env = _environment("http://127.0.0.1:9", 8080, True, True)
    result = subprocess.run([sys.executable, "-c", probe, str(HERE / "agent_langchain.py"), mode],
        env=env, cwd=tmp_path, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
