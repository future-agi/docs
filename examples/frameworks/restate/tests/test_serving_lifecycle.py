"""Real Hypercorn/Restate processes and localhost OTLP, without vendor/model calls."""
import concurrent.futures
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

FIXTURE = Path(__file__).parent / "fixtures/lifecycle_app.py"
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process signals")


def wait_until(condition, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not reached before timeout")


@contextmanager
def collector():
    received = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, dict(self.headers), body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextmanager
def service(tmp_path, endpoint, *, workers=1, delay=0):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = tmp_path / "service.log"
    started = tmp_path / "started"
    # Explicit environment: never inherit real credentials, model URLs, or proxy settings.
    env = {
        "PATH": os.defpath, "HOME": str(tmp_path),
        "FI_API_KEY": "synthetic-api", "FI_SECRET_KEY": "synthetic-secret",
        "FI_BASE_URL": endpoint, "FI_PROJECT_NAME": "restate-lifecycle-test",
        "OPENAI_API_KEY": "synthetic-model", "OPENAI_BASE_URL": "http://127.0.0.1:1",
        "FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true",
        "OTEL_BSP_SCHEDULE_DELAY": "60000", "OTEL_EXPORTER_OTLP_TIMEOUT": "2",
        "PROBE_STARTED": str(started), "PROBE_DELAY": str(delay),
    }
    with log.open("w") as output:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-m", "hypercorn", f"{FIXTURE}:app",
             "--workers", str(workers), "--bind", f"127.0.0.1:{port}",
             "--graceful-timeout", "3"],
            env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
        )
    try:
        wait_until(lambda: "Running on" in log.read_text() or proc.poll() is not None)
        assert proc.poll() is None, log.read_text()
        yield proc, f"http://127.0.0.1:{port}", started
    finally:
        # Always reap this test's process group, including the CLI's spawned worker.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)


def request(url):
    with urllib.request.urlopen(url + "/probe", timeout=10) as response:
        assert response.read() == b"ok"


def assert_wire(received):
    assert len(received) == 1
    path, headers, body = received[0]
    assert path == "/tracer/v1/traces"
    assert {key.lower(): value for key, value in headers.items()}["x-api-key"] == "synthetic-api"
    assert {key.lower(): value for key, value in headers.items()}["x-secret-key"] == "synthetic-secret"
    assert b"PRIVATE_MARKER" not in body
    assert b"synthetic-api" not in body and b"synthetic-secret" not in body
    export = ExportTraceServiceRequest.FromString(body)
    (resource,) = export.resource_spans
    attrs = {item.key: item.value.string_value for item in resource.resource.attributes}
    assert attrs["project_name"] == "restate-lifecycle-test"
    assert attrs["project_type"] == "observe"
    spans = [span for scope in resource.scope_spans for span in scope.spans]
    assert len(spans) == 1  # no duplicate span producer
    (span,) = spans
    assert span.name == "get_weather"
    assert span.trace_id.hex() == "1" * 32
    assert span.parent_span_id.hex() == "2" * 16
    assert {item.key: item.value.string_value for item in span.attributes}["gen_ai.span.kind"] == "TOOL"


def test_unmanaged_worker_loses_sigterm_shutdown(tmp_path):
    """Reproducer: removing the copied handler without replacing serving still hangs."""
    with collector() as (endpoint, received), service(tmp_path, endpoint, workers=0) as (proc, url, _):
        request(url)
        assert not received  # 60-second batch still queued
        proc.terminate()
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=1)
        assert not received  # SIGTERM did not get to provider shutdown


@pytest.mark.parametrize(("sig", "workers"), [(signal.SIGTERM, 1), (signal.SIGINT, 1), (signal.SIGTERM, 2)])
def test_cli_supervisor_exits_and_flushes_buffered_otlp(tmp_path, sig, workers):
    with collector() as (endpoint, received), service(tmp_path, endpoint, workers=workers) as (proc, url, _):
        request(url)
        assert not received
        proc.send_signal(sig)
        assert proc.wait(timeout=10) == 0
        assert_wire(received)


@pytest.mark.parametrize("whole_group", [False, True])
def test_cli_drains_active_request_before_flushing(tmp_path, whole_group):
    with collector() as (endpoint, received), service(tmp_path, endpoint, delay=0.5) as (proc, url, started):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            response = executor.submit(request, url)
            wait_until(started.exists)
            assert not received
            if whole_group:
                os.killpg(proc.pid, signal.SIGTERM)
            else:
                proc.terminate()
            response.result(timeout=10)
        assert proc.wait(timeout=10) == 0
        assert_wire(received)
