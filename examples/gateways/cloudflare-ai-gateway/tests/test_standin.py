"""standin_cloudflare.py against a throwaway local HTTP server: what goes on the wire."""
import gzip
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(HERE, "standin_cloudflare.py")


@pytest.fixture()
def server():
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
            code = 401 if self.headers.get("Authorization") != "Bearer good" else 200
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1/traces", seen
    srv.shutdown()


def run(*args, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True, env=e)


def test_json_is_the_default_and_the_header_value_comes_from_the_environment(server):
    url, seen = server
    r = run("send", "--endpoint", url, "--header", "Authorization=TOK", env={"TOK": "Bearer good"}, )
    assert r.returncode == 0, r.stdout + r.stderr
    assert seen[0]["headers"]["Content-Type"] == "application/json"
    body = json.loads(seen[0]["body"])
    assert body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
    assert "Bearer good" not in r.stdout + r.stderr                 # header values are never printed


def test_headers_json_object_like_the_exporters_headers_field(server):
    url, seen = server
    r = run("send", "--endpoint", url, "--headers", json.dumps({"Authorization": "Bearer good", "X-Extra": "1"}))
    assert r.returncode == 0 and seen[0]["headers"]["X-Extra"] == "1"


def test_protobuf_and_gzip_content_types(server):
    url, seen = server
    run("send", "--endpoint", url, "--headers", '{"Authorization": "Bearer good"}', "--content-type", "protobuf")
    assert seen[0]["headers"]["Content-Type"] == "application/x-protobuf"
    run("send", "--endpoint", url, "--headers", '{"Authorization": "Bearer good"}', "--gzip")
    assert seen[1]["headers"]["Content-Encoding"] == "gzip"
    assert json.loads(gzip.decompress(seen[1]["body"]))["resourceSpans"]


def test_a_401_is_reported_and_exit_status_is_1(server):
    url, _ = server
    r = run("send", "--endpoint", url)
    assert r.returncode == 1 and json.loads(r.stdout.splitlines()[0])["status"] == 401


def test_marker_reaches_prompt_completion_and_error_text(server):
    url, seen = server
    H = '{"Authorization": "Bearer good"}'
    run("send", "--endpoint", url, "--headers", H, "--marker", "CFGZZ1")
    run("send", "--endpoint", url, "--headers", H, "--marker", "CFGZZ2", "--scenario", "error", "--exception-event")
    ok, err = seen[0]["body"].decode(), seen[1]["body"].decode()
    assert ok.count("CFGZZ1") >= 2                                   # prompt and completion
    assert "CFGZZ2" in err and "cfgzz2@example.test" in err and "Traceback" in err


def test_trace_headers_and_resource_flags(server):
    url, seen = server
    tid, sid = "0123456789abcdef0123456789abcdef", "0123456789abcdef"
    run("send", "--endpoint", url, "--headers", '{"Authorization": "Bearer good"}', "--otel-trace-id", tid, "--otel-parent-span-id", sid, "--resource", "project_name=p1")
    body = json.loads(seen[0]["body"])
    sp = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert sp["traceId"] == tid and sp["parentSpanId"] == sid
    assert {"key": "project_name", "value": {"stringValue": "p1"}} in body["resourceSpans"][0]["resource"]["attributes"]


def test_a_bad_trace_id_is_refused_before_anything_is_sent(server):
    url, seen = server
    r = run("send", "--endpoint", url, "--otel-trace-id", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    assert r.returncode != 0 and not seen


def test_missing_environment_variable_is_a_clear_error(server):
    url, _ = server
    r = run("send", "--endpoint", url, "--header", "Authorization=NOPE_NOT_SET", env={})
    assert r.returncode != 0 and "NOPE_NOT_SET" in r.stderr
