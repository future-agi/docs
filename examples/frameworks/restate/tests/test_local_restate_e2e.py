"""Optional localhost E2E: real Restate server, script entry point and OTLP wire.

RESTATE_SERVER=/path/to/restate-server pytest tests/test_local_restate_e2e.py

A local fake model and OTLP receiver are used; no model provider or Future AGI is called.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

EXAMPLE = Path(__file__).resolve().parents[1]
RESTATE_SERVER = os.environ.get("RESTATE_SERVER")
pytestmark = pytest.mark.skipif(not RESTATE_SERVER, reason="set RESTATE_SERVER to a restate-server binary")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until(condition, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if condition():
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError("condition was not reached before timeout")


@contextmanager
def http_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def otlp_receiver(received):
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            pass

    return Receiver


class FakeModel(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if request.get("tools"):
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city":"PRIVATE_MARKER"}'},
            }]}
        else:
            message = {"role": "assistant", "content": "Sunny in the synthetic city."}
        body = json.dumps({
            "id": "chatcmpl-local", "object": "chat.completion", "created": 1,
            "model": request["model"], "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@contextmanager
def process(args, env, log):
    with log.open("w") as output:
        proc = subprocess.Popen(args, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        yield proc
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)


def post(url, payload):
    request = urllib.request.Request(url, json.dumps(payload).encode(), {"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read())


def spans(received):
    out = []
    for _path, headers, body in received:
        for resource_spans in ExportTraceServiceRequest.FromString(body).resource_spans:
            resource = {a.key: a.value.string_value for a in resource_spans.resource.attributes}
            for scope_spans in resource_spans.scope_spans:
                out.extend((headers, resource, span) for span in scope_spans.spans)
    return out


def test_script_entry_point_flushes_service_spans_under_restate_attempts(tmp_path):
    received = []
    ports = {name: free_port() for name in ("service", "ingress", "admin", "fabric")}
    base_env = {"PATH": os.defpath, "HOME": str(tmp_path), "PYTHONNOUSERSITE": "1"}
    with ExitStack() as stack:
        receiver = stack.enter_context(http_server(otlp_receiver(received)))
        model = stack.enter_context(http_server(FakeModel))
        endpoint = f"http://127.0.0.1:{receiver.server_port}"
        restate = stack.enter_context(process([RESTATE_SERVER, "--base-dir", str(tmp_path / "restate")], {
            **base_env,
            "RESTATE_LISTEN_MODE": "tcp", "RESTATE_BIND_IP": "127.0.0.1",
            "RESTATE_BIND_PORT": str(ports["fabric"]),
            "RESTATE_ADMIN__BIND_PORT": str(ports["admin"]),
            "RESTATE_INGRESS__BIND_PORT": str(ports["ingress"]),
            "RESTATE_TRACING_ENDPOINT": f"otlp+{endpoint}/tracer/v1/traces",
            "RESTATE_TRACING_HEADERS": '{X-Api-Key="synthetic-api", X-Secret-Key="synthetic-secret"}',
            "OTEL_RESOURCE_ATTRIBUTES": "project_name=restate-local,project_type=observe",
        }, tmp_path / "restate.log"))
        wait_until(lambda: urllib.request.urlopen(f"http://127.0.0.1:{ports['admin']}/health", timeout=1).status == 200)
        service = stack.enter_context(process([sys.executable, str(EXAMPLE / "agent_service.py")], {
            **base_env,
            "FI_API_KEY": "synthetic-api", "FI_SECRET_KEY": "synthetic-secret", "FI_BASE_URL": endpoint,
            "FI_PROJECT_NAME": "restate-local", "FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true",
            "FI_HIDE_INPUT_MESSAGES": "true", "FI_HIDE_OUTPUT_MESSAGES": "true",
            "OPENAI_API_KEY": "synthetic-model", "OPENAI_BASE_URL": f"http://127.0.0.1:{model.server_port}/v1",
            "MODEL": "synthetic-model", "SERVICE_PORT": str(ports["service"]),
            "OTEL_BSP_SCHEDULE_DELAY": "60000",
        }, tmp_path / "service.log"))
        wait_until(lambda: "Running on" in (tmp_path / "service.log").read_text())

        assert post(f"http://127.0.0.1:{ports['admin']}/deployments",
                    {"uri": f"http://127.0.0.1:{ports['service']}"})[0] == 201
        status, answer = post(f"http://127.0.0.1:{ports['ingress']}/WeatherAgent/PRIVATE_MARKER/ask",
                              {"question": "PRIVATE_MARKER weather?", "flaky": True})
        assert status == 200 and answer == {"answer": "Sunny in the synthetic city."}
        # Restate exports its own batch on a timer; the service's 60-second batch is still buffered.
        wait_until(lambda: any(s.name.startswith("invocation-end") for _h, _r, s in spans(received)), timeout=30)
        assert not [s for _h, _r, s in spans(received) if s.name in {"ChatCompletion", "get_weather"}]

        service.terminate()
        assert service.wait(timeout=40) == 0
        restate.terminate()
        assert restate.wait(timeout=40) == 0

    exported = spans(received)
    (tmp_path / "spans.json").write_text(json.dumps([
        {"name": s.name, "trace": s.trace_id.hex(), "span": s.span_id.hex(), "parent": s.parent_span_id.hex(),
         "project": r.get("project_name")} for _h, r, s in exported
    ], indent=1))
    assert all(path == "/tracer/v1/traces" for path, _headers, _body in received)
    assert all(h["x-api-key"] == "synthetic-api" and h["x-secret-key"] == "synthetic-secret"
               for _path, h, _body in received)
    assert all(r.get("project_name") == "restate-local" and r.get("project_type") == "observe"
               for _h, r, _s in exported)
    attempts = {s.span_id: s for _h, _r, s in exported if s.name.startswith("invocation-attempt")}
    service_spans = [s for _h, _r, s in exported if s.name in {"ChatCompletion", "get_weather"}]
    # The service's hide switches apply on the wire. Restate's own key fields are why the guide keeps the collector.
    assert all(b"PRIVATE_MARKER" not in s.SerializeToString() for s in service_spans)
    assert len(attempts) == 2
    assert [s.name for s in service_spans].count("ChatCompletion") == 2  # plan was journaled, not replayed
    assert [s.name for s in service_spans].count("get_weather") == 2  # failed run plus retry
    assert len({s.trace_id for s in service_spans}) == 1
    assert all(s.parent_span_id in attempts and s.trace_id == attempts[s.parent_span_id].trace_id
               for s in service_spans)
