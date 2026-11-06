"""Replay a recorded SDK export through the real collector (otelcol.yaml) and check what leaves it.

The fixture is what ibm-watsonx-orchestrate-sdk 2.18.2 sent from agent.py in one end-to-end run
(an answer with a failed tool call, a failed model call, and a Client-mode run), converted to
OTLP/JSON, with the run's marker, e-mail user id and local paths replaced by fixture values.
The Client-mode request is replayed with an Authorization bearer header, as the SDK sent it.

Needs Docker, and a Docker that can reach the host's 127.0.0.1 through host.docker.internal
(Docker Desktop, colima). Opt in with RUN_DOCKER_TESTS=1.
"""
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import wire_tap

EXAMPLE = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wxo_sdk_2.18.2_requests.json"
IMAGE = os.environ.get("COLLECTOR_IMAGE", "otel/opentelemetry-collector-contrib:0.162.0")
KEY_A, KEY_B = "fixture-key-a-" + uuid.uuid4().hex[:8], "fixture-key-b-" + uuid.uuid4().hex[:8]
BEARER = "fixture-bearer-" + uuid.uuid4().hex
MARKER, EMAIL, HOME = "wxoFIXTUREmarker", "fixture.user@example.com", "/home/dev"

pytestmark = pytest.mark.skipif(os.environ.get("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1 (needs Docker)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _attrs(items) -> dict:
    return {a["key"]: next(iter(a["value"].values()), None) for a in items}


def _post(port: int, body: dict, bearer: bool) -> None:
    headers = {"content-type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {BEARER}"
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/traces", data=json.dumps(body).encode(), headers=headers)
    urllib.request.urlopen(req, timeout=5)


def _replay(tmp_path, monkeypatch, *extra_env: str) -> list[dict]:
    monkeypatch.setenv("TAP_EXPECT_API_KEY", KEY_A)
    monkeypatch.setenv("TAP_EXPECT_SECRET_KEY", KEY_B)
    out = tmp_path / "wire.jsonl"
    tap = ThreadingHTTPServer(("127.0.0.1", 0), wire_tap.make_handler(str(out), None, False))
    threading.Thread(target=tap.serve_forever, daemon=True).start()
    port, name = _free_port(), f"{os.environ.get('COLLECTOR_NAME', 'wxo-adk-otelcol-test')}-{uuid.uuid4().hex[:6]}"
    env = ["-e", f"FI_TRACES_URL=http://host.docker.internal:{tap.server_address[1]}/tracer/v1/traces",
           "-e", "FI_PROJECT_NAME=fixture-project", "-e", f"FI_API_KEY={KEY_A}", "-e", f"FI_SECRET_KEY={KEY_B}"]
    for e in extra_env:
        env += ["-e", e]
    subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "--memory", "256m", "-p", f"127.0.0.1:{port}:4318",
                    "-v", f"{EXAMPLE / 'otelcol.yaml'}:/etc/otelcol.yaml:ro", *env, IMAGE, "--config", "/etc/otelcol.yaml"],
                   check=True, capture_output=True)
    requests = json.loads(FIXTURE.read_text())
    try:
        deadline = time.time() + 30
        while True:
            try:
                _post(port, requests[0]["body"], requests[0]["authorization"])
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        for r in requests[1:]:
            _post(port, r["body"], r["authorization"])
        sent = sum(len(ss["spans"]) for r in requests for rs in r["body"]["resourceSpans"] for ss in rs["scopeSpans"])
        while time.time() < deadline:
            lines = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
            if sum(len(_spans(rec)) for rec in lines) >= sent:
                return lines
            time.sleep(0.3)
        raise AssertionError("collector did not forward every span")
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        tap.shutdown()


def _spans(rec: dict) -> list[dict]:
    return [sp for rs in rec["body"]["resourceSpans"] for ss in rs["scopeSpans"] for sp in ss["spans"]]


def test_fixture_is_what_the_sdk_sent():
    requests = json.loads(FIXTURE.read_text())
    text = json.dumps(requests)
    assert sum(r["authorization"] for r in requests) == 1
    assert MARKER in text and EMAIL in text and "exception.stacktrace" in text and "Unknown User" in text
    assert "project_name" not in text  # the SDK never sets it


def test_default_names_project_maps_kinds_and_removes_content(tmp_path, monkeypatch):
    lines = _replay(tmp_path, monkeypatch)
    for rec in lines:
        assert rec["content_encoding"] is None
        assert rec["has_key_headers"] and rec["key_values_match"]
        assert "authorization" not in rec["header_names"]
    text = json.dumps([rec["body"] for rec in lines])
    for needle in (BEARER, KEY_A, KEY_B, MARKER, EMAIL, HOME, "exception.stacktrace", "exception.message",
                   "Unknown User", "input.value", "output.value", "user.id"):
        assert needle not in text, needle
    for rec in lines:
        for rs in rec["body"]["resourceSpans"]:
            res = _attrs(rs["resource"]["attributes"])
            assert res["project_name"] == "fixture-project" and res["project_type"] == "observe"
            assert res["service.name"] == "weather-agent"
    spans = [sp for rec in lines for sp in _spans(rec)]
    kinds = {"llm": "LLM", "tool": "TOOL", "agent": "AGENT", "root": "CHAIN"}
    for sp in spans:
        a = _attrs(sp.get("attributes", []))
        assert a["fi.span.kind"] == kinds[a["span.kind"]]
        if a["span.kind"] == "llm":
            assert a["gen_ai.provider.name"] == "openai"
        if a["span.kind"] == "root":
            assert a["session.id"] == a["conversation.id"]
        if sp.get("status", {}).get("code") == "STATUS_CODE_ERROR":
            assert sp["status"]["message"] == "error"
    assert sum(1 for sp in spans if sp.get("status", {}).get("code") == "STATUS_CODE_ERROR") == 4


def test_opt_in_keeps_content_and_user_ids_but_never_stack_traces(tmp_path, monkeypatch):
    lines = _replay(tmp_path, monkeypatch, "KEEP_WXO_CONTENT=true")
    text = json.dumps([rec["body"] for rec in lines])
    assert MARKER in text and EMAIL in text and "input.value" in text and "exception.message" in text
    for needle in (BEARER, HOME, "exception.stacktrace", "Unknown User"):
        assert needle not in text, needle
    assert all("authorization" not in rec["header_names"] for rec in lines)
