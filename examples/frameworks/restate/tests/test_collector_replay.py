"""Replay one recorded Restate 1.8.0 trace through the real collector (otelcol.yaml) and check what leaves it.

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
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "restate_1.8.0_keyed_failure.json"
IMAGE = os.environ.get("COLLECTOR_IMAGE", "otel/opentelemetry-collector-contrib:0.162.0")
KEY_A, KEY_B = "fixture-key-a-" + uuid.uuid4().hex[:8], "fixture-key-b-" + uuid.uuid4().hex[:8]

pytestmark = pytest.mark.skipif(os.environ.get("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1 (needs Docker)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _attrs(items) -> dict:
    return {a["key"]: next(iter(a["value"].values()), None) for a in items}


def _replay(tmp_path, monkeypatch, *extra_env: str) -> dict:
    monkeypatch.setenv("TAP_EXPECT_API_KEY", KEY_A)
    monkeypatch.setenv("TAP_EXPECT_SECRET_KEY", KEY_B)
    out = tmp_path / "wire.jsonl"
    tap = ThreadingHTTPServer(("127.0.0.1", 0), wire_tap.make_handler(str(out), None, False))
    threading.Thread(target=tap.serve_forever, daemon=True).start()
    port, name = _free_port(), f"{os.environ.get('COLLECTOR_NAME', 'restate-otelcol-test')}-{uuid.uuid4().hex[:6]}"
    env = ["-e", f"FI_TRACES_URL=http://host.docker.internal:{tap.server_address[1]}/tracer/v1/traces",
           "-e", "FI_PROJECT_NAME=fixture-project"]
    for e in extra_env:
        env += ["-e", e]
    subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "--memory", "256m", "-p", f"127.0.0.1:{port}:4318",
                    "-v", f"{EXAMPLE / 'otelcol.yaml'}:/etc/otelcol.yaml:ro", *env, IMAGE, "--config", "/etc/otelcol.yaml"],
                   check=True, capture_output=True)
    try:
        body = FIXTURE.read_bytes()
        deadline = time.time() + 30
        while True:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/tracer/v1/traces", data=body, headers={
                    "content-type": "application/json", "X-Api-Key": KEY_A, "X-Secret-Key": KEY_B})
                urllib.request.urlopen(req, timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        while not (out.exists() and out.read_text().strip()) and time.time() < deadline:
            time.sleep(0.3)
        return json.loads(out.read_text().splitlines()[0])
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        tap.shutdown()


def _spans(rec: dict) -> list[dict]:
    return [sp for rs in rec["body"]["resourceSpans"] for ss in rs["scopeSpans"] for sp in ss["spans"]]


def test_default_stamps_project_passes_headers_and_removes_details(tmp_path, monkeypatch):
    rec = _replay(tmp_path, monkeypatch)
    assert rec["content_encoding"] is None
    assert rec["has_key_headers"] and rec["key_values_match"]
    text = json.dumps(rec["body"])
    assert KEY_A not in text and KEY_B not in text  # keys travel as headers only, never as attributes
    res = _attrs(rec["body"]["resourceSpans"][0]["resource"]["attributes"])
    assert res["project_name"] == "fixture-project" and res["project_type"] == "observe"
    assert "service.instance.id" not in res and res["service.name"] == "Restate"
    spans = _spans(rec)
    assert len(spans) == 8
    for sp in spans:
        a = _attrs(sp.get("attributes", []))
        assert a["restate.invocation.target"] == "Counter/{key}/add"
        for gone in ("restate.deployment.address", "client.socket.address", "client.socket.port", "error.message"):
            assert gone not in a
    end = [sp for sp in spans if sp["name"].startswith("invocation-end") and sp.get("status", {}).get("code") == "STATUS_CODE_ERROR"]
    assert end and end[0]["status"]["message"] == "error"
    for needle in ("alice@example.com", "card 4242", "weather-agent.internal", "10.0.0.9", "build-host-7"):
        assert needle not in text


def test_opt_in_keeps_error_text_and_keys_but_still_removes_hosts(tmp_path, monkeypatch):
    rec = _replay(tmp_path, monkeypatch, "KEEP_RESTATE_DETAILS=true")
    text = json.dumps(rec["body"])
    assert "Counter/alice@example.com/add" in text and "card 4242 declined" in text
    for needle in ("weather-agent.internal", "10.0.0.9", "build-host-7"):
        assert needle not in text
