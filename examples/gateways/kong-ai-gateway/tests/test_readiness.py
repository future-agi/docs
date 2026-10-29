"""lib.sh readiness wait (start_kong), with fake `docker` and `curl` on PATH (no Docker needed).

Regression for a flaky E2E: start_kong used to poll /status for a fixed 60 s and then sleep 6 s, which failed on a
loaded host. It now polls Kong's readiness endpoint (GET /status/ready on the Status API) with a configurable
timeout (KONG_READY_TIMEOUT, default 300 s), stops at once if the container exits, and prints Kong's last log
lines (key values redacted) when Kong does not become ready.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "lib.sh"
SECRET = "fake-secret-value-123456"

FAKE_CURL = """#!/bin/sh
echo "$@" >> "$FAKE_DIR/curl.calls"
n=$(cat "$FAKE_DIR/curl.count" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/curl.count"
if [ "${FAKE_READY_AFTER:-0}" -gt 0 ] && [ "$n" -ge "$FAKE_READY_AFTER" ]; then exit 0; fi
exit 22
"""
FAKE_DOCKER = """#!/bin/sh
echo "$@" >> "$FAKE_DIR/docker.calls"
case "$1" in
  run) echo fake-container-id ;;
  inspect) cat "$FAKE_DIR/state" 2>/dev/null || echo running ;;
  logs)
    n=$3; i=$((100 - n + 1))
    while [ "$i" -le 100 ]; do echo "fake kong log line $i"; i=$((i + 1)); done
    echo "exporter header X-Secret-Key: $FI_SECRET_KEY" ;;
esac
exit 0
"""

BASHES = sorted({b for b in (shutil.which("bash"), "/bin/bash") if b and os.path.exists(b)})


@pytest.fixture
def fake(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("curl", FAKE_CURL), ("docker", FAKE_DOCKER)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    return tmp_path


def run(fake, bash, script, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("KONG_", "FAKE_"))}
    e.update(PATH=f"{fake / 'bin'}:{os.environ['PATH']}", FAKE_DIR=str(fake), EVID=str(fake / "evid"),
             KONG_READY_POLL="0.05", FI_SECRET_KEY=SECRET, FI_API_KEY="fake-api-key-abcdef", UPSTREAM_API_KEY="")
    e.update(env)
    t0 = time.monotonic()
    p = subprocess.run([bash, "-c", f'source "{LIB}"; {script}'], env=e, capture_output=True, text=True, timeout=60)
    return p, time.monotonic() - t0


@pytest.mark.parametrize("bash", BASHES)
def test_polls_status_ready_until_200_then_returns(fake, bash):
    p, _ = run(fake, bash, "start_kong /dev/null", FAKE_READY_AFTER="3")
    assert p.returncode == 0, p.stderr
    assert "Kong ready after" in p.stdout
    calls = (fake / "curl.calls").read_text().splitlines()
    assert len(calls) == 3
    assert all("http://127.0.0.1:18012/status/ready" in c and "-fs" in c.split() for c in calls)  # -f: 503 is not ready
    run_args = next(c for c in (fake / "docker.calls").read_text().splitlines() if c.startswith("run "))
    assert "KONG_STATUS_LISTEN=0.0.0.0:8007" in run_args and "127.0.0.1:18012:8007" in run_args
    assert "Kong ready after" in (fake / "evid" / "readiness.txt").read_text()


@pytest.mark.parametrize("bash", BASHES)
def test_timeout_fails_and_prints_last_log_lines_redacted(fake, bash):
    p, took = run(fake, bash, "start_kong /dev/null", KONG_READY_TIMEOUT="1", KONG_LOG_TAIL="5")
    assert p.returncode == 1
    assert "Kong did not become ready within 1s" in p.stderr
    assert "fake kong log line 96" in p.stderr and "fake kong log line 100" in p.stderr
    assert "fake kong log line 95" not in p.stderr
    assert SECRET not in p.stderr + p.stdout and "<redacted>" in p.stderr
    assert 1 <= took < 20


@pytest.mark.parametrize("bash", BASHES)
def test_exited_container_fails_fast_without_waiting_for_the_timeout(fake, bash):
    (fake / "state").write_text("exited\n")
    p, took = run(fake, bash, "start_kong /dev/null", KONG_READY_TIMEOUT="300")
    assert p.returncode == 1
    assert "container kong-fi-e2e is exited" in p.stderr
    assert "fake kong log line 100" in p.stderr
    assert took < 20


@pytest.mark.parametrize("bash", BASHES)
def test_timeout_and_status_port_are_configurable_with_minutes_by_default(fake, bash):
    p, _ = run(fake, bash, 'echo "$KONG_READY_TIMEOUT $KONG_STATUS_PORT"')
    timeout, port = p.stdout.split()
    assert int(timeout) >= 300 and port == "18012"
    p, _ = run(fake, bash, "start_kong /dev/null", FAKE_READY_AFTER="1", KONG_STATUS_PORT="19999")
    assert p.returncode == 0 and "127.0.0.1:19999/status/ready" in (fake / "curl.calls").read_text()
