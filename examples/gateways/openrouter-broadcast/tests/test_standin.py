"""The sender stand-in against a loopback HTTP server: what it puts on the wire, and what it prints."""
import gzip
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import standin_openrouter as so

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "standin_openrouter.py")


class Recorder(BaseHTTPRequestHandler):
    log: list = []
    status = 200

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        Recorder.log.append({"path": self.path, "headers": dict(self.headers), "body": body})
        self.send_response(Recorder.status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture()
def server():
    Recorder.log = []
    Recorder.status = 200
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/v1/traces"
    httpd.shutdown()


def run(*args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=e)


def body_of(entry):
    raw = entry["body"]
    if entry["headers"].get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def test_probe_posts_an_empty_payload_with_the_test_header(server):
    r = run("probe", "--endpoint", server, "--headers", '{"Authorization": "Bearer t"}')
    assert r.returncode == 0
    sent = Recorder.log[0]
    assert body_of(sent) == {"resourceSpans": []}
    assert sent["headers"]["X-Test-Connection"] == "true"
    assert sent["headers"]["Content-Type"] == "application/json"
    assert sent["headers"]["Authorization"] == "Bearer t"


@pytest.mark.parametrize("status,passes", [(200, True), (204, True), (400, True), (401, False), (403, False), (500, False)])
def test_probe_uses_the_two_xx_or_400_rule(server, status, passes):
    Recorder.status = status
    r = run("probe", "--endpoint", server)
    assert (r.returncode == 0) is passes
    assert json.loads(r.stdout)["passes_openrouter_rule"] is passes


def test_headers_json_and_env_headers_merge_and_values_are_never_printed(server):
    r = run("send", "--endpoint", server, "--headers", '{"X-Custom": "visible-config"}', "--header", "X-Secret=SECRET_VAR",
            env={"SECRET_VAR": "super-secret-value"})
    assert r.returncode == 0
    sent = Recorder.log[0]["headers"]
    assert sent["X-Custom"] == "visible-config" and sent["X-Secret"] == "super-secret-value"
    assert "super-secret-value" not in r.stdout + r.stderr


def test_header_with_missing_env_var_is_an_error(server):
    r = run("send", "--endpoint", server, "--header", "X-Secret=NO_SUCH_VAR_8244")
    assert r.returncode != 0 and "NO_SUCH_VAR_8244" in r.stderr


def test_headers_must_be_a_json_object(server):
    assert run("probe", "--endpoint", server, "--headers", '["a"]').returncode != 0


def test_send_posts_one_trace_json_and_prints_its_id(server):
    r = run("send", "--endpoint", server, "--scenario", "success", "--marker", "ORBTEST1", "--resource", "project_name=p1")
    assert r.returncode == 0
    line = json.loads(r.stdout.splitlines()[0])
    body = body_of(Recorder.log[0])
    spans = body["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert line["status"] == 200 and line["trace_id"] == spans[0]["traceId"]
    assert "ORBTEST1" in json.dumps(body)
    res = {a["key"]: a["value"].get("stringValue") for a in body["resourceSpans"][0]["resource"]["attributes"]}
    assert res["project_name"] == "p1"


def test_gzip_flag_compresses_the_body(server):
    run("send", "--endpoint", server, "--gzip")
    assert Recorder.log[0]["headers"]["Content-Encoding"] == "gzip"
    assert "resourceSpans" in body_of(Recorder.log[0])


def test_repeat_sends_the_identical_body(server):
    run("send", "--endpoint", server, "--repeat", "2")
    assert Recorder.log[0]["body"] == Recorder.log[1]["body"]


def test_privacy_scenario_sends_no_prompt_or_completion(server):
    run("send", "--endpoint", server, "--scenario", "privacy", "--marker", "ORBTEST2")
    assert "ORBTEST2" not in Recorder.log[0]["body"].decode()


def test_error_scenario_marks_the_generation_failed_and_can_add_an_exception_event(server):
    run("send", "--endpoint", server, "--scenario", "error", "--marker", "ORBTEST3", "--exception-event")
    gen = body_of(Recorder.log[0])["resourceSpans"][0]["scopeSpans"][0]["spans"][-1]
    assert gen["status"]["code"] == 2 and "ORBTEST3" in gen["status"]["message"]
    assert gen["events"][0]["name"] == "exception"


def test_rejected_post_exits_nonzero_and_shows_the_status_and_a_body_snippet(server):
    Recorder.status = 400
    r = run("send", "--endpoint", server)
    assert r.returncode == 1 and json.loads(r.stdout.splitlines()[0])["status"] == 400


def test_connection_failure_is_status_zero_not_a_traceback():
    r = run("send", "--endpoint", "http://127.0.0.1:9/v1/traces")
    assert r.returncode == 1 and json.loads(r.stdout.splitlines()[0])["status"] == 0 and "Traceback" not in r.stderr


def test_parse_headers_unit():
    os.environ["T8244"] = "x"
    assert so.parse_headers('{"A": 1}', ["B=T8244"]) == {"A": "1", "B": "x"}
