"""lib.sh readiness waits, with fake `docker` and `curl` on PATH (no Docker needed).

Regression for a flaky E2E: the Management API and Gateway waits were fixed loops of about 180 s and the Collector
got a fixed 3 s sleep, so the run failed on a loaded host (load average 50-70). Every start now polls the
component's own readiness signal (MongoDB ping, `/_node/health` on the Management API and on the Gateway with the
`sync-process` probe, the Collector's OTLP receiver) for up to READY_TIMEOUT (default 600 s, per-component
overrides), stops at once when the container exits, and prints the container's last log lines (key values
redacted) when it gives up.
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "lib.sh"
SECRET = "fake-secret-value-123456"
HEALTHY = {"http-server": {"healthy": True}, "sync-process": {"healthy": True}}

FAKE_CURL = """#!/bin/sh
echo "$@" >> "$FAKE_DIR/curl.calls"
for a in "$@"; do url=$a; done
case "$url" in
  *fi-untraced*)
    # the first FAKE_UNTRACED_SILENT calls get no answer (curl prints 000 after its -m timeout)
    n=$(cat "$FAKE_DIR/untraced.count" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/untraced.count"
    if [ "$n" -le "${FAKE_UNTRACED_SILENT:-0}" ]; then code=000
    else code=$(cat "$FAKE_DIR/untraced.code" 2>/dev/null || echo 200); fi ;;
  */v1/traces) code=$(cat "$FAKE_DIR/otelcol.code" 2>/dev/null || echo 401) ;;
  *) code=200 ;;
esac
case "$*" in *http_code*) printf '%s' "$code" ;; esac
exit 0
"""
# `docker exec <c> ...` (health curl or mongosh ping) succeeds and prints health.json once the exec count reaches
# FAKE_HEALTHY_AFTER; before that it fails like `curl -f` on Gravitee's HTTP 500 for an unhealthy probe.
# `docker logs --tail N` prints N numbered lines plus a line with a secret value.
FAKE_DOCKER = """#!/bin/sh
echo "$@" >> "$FAKE_DIR/docker.calls"
case "$1" in
  run) echo fake-container-id ;;
  ps) cat "$FAKE_DIR/ps" 2>/dev/null ;;
  inspect) cat "$FAKE_DIR/state" 2>/dev/null || echo running ;;
  exec)
    n=$(cat "$FAKE_DIR/exec.count" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/exec.count"
    if [ "$n" -ge "${FAKE_HEALTHY_AFTER:-1}" ]; then cat "$FAKE_DIR/health.json"; else exit 22; fi ;;
  logs)
    n=$3; i=$((100 - n + 1))
    while [ "$i" -le 100 ]; do echo "fake log line $i"; i=$((i + 1)); done
    echo "exporter header X-Secret-Key: $FI_SECRET_KEY" ;;
esac
exit 0
"""

BASHES = sorted({b for b in (shutil.which("bash"), "/bin/bash") if b and os.path.exists(b)})
TIMEOUT_VARS = ("READY_TIMEOUT", "MONGO_READY_TIMEOUT", "MAPI_READY_TIMEOUT", "GW_READY_TIMEOUT",
                "OTELCOL_READY_TIMEOUT", "GW_API_GRACE", "READY_POLL", "LOG_TAIL", "OTELCOL_PORT", "PREFIX")


@pytest.fixture
def fake(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("curl", FAKE_CURL), ("docker", FAKE_DOCKER)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    (tmp_path / "health.json").write_text(json.dumps(HEALTHY))
    return tmp_path


def run(fake, bash, script, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_") and k not in TIMEOUT_VARS}
    e.update(PATH=f"{fake / 'bin'}:{os.environ['PATH']}", FAKE_DIR=str(fake), EVID=str(fake / "evid"),
             READY_POLL="0.05", FI_SECRET_KEY=SECRET, FI_API_KEY="fake-api-key-abcdef", PY=shutil.which("python3"))
    e.update(env)
    t0 = time.monotonic()
    p = subprocess.run([bash, "-c", f'set -o pipefail; source "{LIB}"; {script}'], env=e, capture_output=True,
                       text=True, timeout=60)
    return p, time.monotonic() - t0


@pytest.mark.parametrize("bash", BASHES)
def test_gateway_waits_for_the_sync_probe_then_checks_the_api(fake, bash):
    p, _ = run(fake, bash, "start_gateway /dev/null", FAKE_HEALTHY_AFTER="3")
    assert p.returncode == 0, p.stderr
    assert "Gateway ready after" in p.stdout
    execs = [c for c in (fake / "docker.calls").read_text().splitlines() if c.startswith("exec ")]
    assert len(execs) == 3
    assert all("gravitee-fi-e2e-gw curl" in c and "/_node/health?probes=http-server,sync-process" in c for c in execs)
    assert "127.0.0.1:18082/fi-untraced/" in (fake / "curl.calls").read_text()
    assert "Gateway ready after" in (fake / "evid" / "readiness.txt").read_text()


@pytest.mark.parametrize("bash", BASHES)
def test_gateway_synced_but_api_missing_is_a_failure_not_a_pass(fake, bash):
    (fake / "untraced.code").write_text("404")
    p, took = run(fake, bash, "start_gateway /dev/null", GW_API_GRACE="1", LOG_TAIL="3")
    assert p.returncode == 1
    assert "/fi-untraced/ answers HTTP 404: the test APIs are not deployed" in p.stderr
    assert "fake log line 100" in p.stderr
    assert took < 20


@pytest.mark.parametrize("bash", BASHES)
def test_gateway_slow_first_answer_does_not_use_up_the_api_grace(fake, bash):
    # Under load the first proxied requests can take longer than curl's 5 s (code 000). That is slowness, not a
    # missing API, so it is bounded by GW_READY_TIMEOUT, not by GW_API_GRACE (0 here would fail within a second).
    p, _ = run(fake, bash, "start_gateway /dev/null", FAKE_UNTRACED_SILENT="30", GW_API_GRACE="0")
    assert p.returncode == 0, p.stderr
    assert int((fake / "untraced.count").read_text()) == 31


@pytest.mark.parametrize("bash", BASHES)
def test_gateway_api_never_answering_fails_at_the_ready_timeout(fake, bash):
    p, took = run(fake, bash, "start_gateway /dev/null", FAKE_UNTRACED_SILENT="1000000", GW_READY_TIMEOUT="1",
                  LOG_TAIL="3")
    assert p.returncode == 1
    assert "/fi-untraced/ did not answer within 1s (raise GW_READY_TIMEOUT" in p.stderr
    assert "not deployed" not in p.stderr
    assert "fake log line 100" in p.stderr and SECRET not in p.stderr
    assert 1 <= took < 20


@pytest.mark.parametrize("bash", BASHES)
def test_timeout_fails_and_prints_last_log_lines_redacted(fake, bash):
    p, took = run(fake, bash, "start_gateway /dev/null", FAKE_HEALTHY_AFTER="1000000", GW_READY_TIMEOUT="1",
                  LOG_TAIL="5")
    assert p.returncode == 1
    assert "Gateway did not become ready within 1s (raise GW_READY_TIMEOUT or READY_TIMEOUT" in p.stderr
    assert "fake log line 96" in p.stderr and "fake log line 100" in p.stderr
    assert "fake log line 95" not in p.stderr
    assert SECRET not in p.stderr + p.stdout and "<redacted>" in p.stderr
    assert 1 <= took < 20


@pytest.mark.parametrize("bash", BASHES)
@pytest.mark.parametrize("fn,label", [("start_gateway /dev/null", "Gateway"), ("start_mapi", "Management API"),
                                      ("start_otelcol", "Collector"), ("start_mongo", "MongoDB")])
def test_exited_container_fails_fast_without_waiting_for_the_timeout(fake, bash, fn, label):
    (fake / "state").write_text("exited\n")
    (fake / "otelcol.code").write_text("000")
    p, took = run(fake, bash, fn, FAKE_HEALTHY_AFTER="1000000", READY_TIMEOUT="300")   # every probe fails
    assert p.returncode == 1
    assert f"{label} did not become ready: container" in p.stderr and "is exited" in p.stderr
    assert "fake log line 100" in p.stderr and SECRET not in p.stderr
    assert took < 20


@pytest.mark.parametrize("bash", BASHES)
def test_collector_ready_only_when_its_receiver_answers(fake, bash):
    (fake / "otelcol.code").write_text("000")             # nothing listening yet
    p, _ = run(fake, bash, "otelcol_ready")
    assert p.returncode == 1
    (fake / "otelcol.code").write_text("401")             # receiver up, bearer-token auth rejects the probe
    p, _ = run(fake, bash, "start_otelcol")
    assert p.returncode == 0, p.stderr
    assert "Collector ready after" in p.stdout
    assert "-X POST http://127.0.0.1:18084/v1/traces" in (fake / "curl.calls").read_text()
    run_args = next(c for c in (fake / "docker.calls").read_text().splitlines() if c.startswith("run "))
    assert "127.0.0.1:18084:4318" in run_args


@pytest.mark.parametrize("bash", BASHES)
@pytest.mark.parametrize("body,probes,ok", [
    (HEALTHY, "http-server sync-process", True),
    ({**HEALTHY, "sync-process": {"healthy": False}}, "http-server sync-process", False),
    ({"http-server": {"healthy": True}}, "http-server sync-process", False),   # unknown/missing probe never passes
    ({"management-repository": {"healthy": True}, "gravitee-apis": {"healthy": True}}, "", True),
    ({"management-repository": {"healthy": True}, "gravitee-apis": {"healthy": False}}, "", False),
    ({}, "", False),
])
def test_probes_healthy(fake, bash, body, probes, ok):
    (fake / "body.json").write_text(json.dumps(body))
    p, _ = run(fake, bash, f'probes_healthy {probes} < "{fake / "body.json"}"')
    assert (p.returncode == 0) is ok, p.stderr


@pytest.mark.parametrize("bash", BASHES)
def test_timeouts_default_to_minutes_and_are_configurable(fake, bash):
    show = 'echo "$MONGO_READY_TIMEOUT $MAPI_READY_TIMEOUT $GW_READY_TIMEOUT $OTELCOL_READY_TIMEOUT"'
    p, _ = run(fake, bash, show)
    assert [int(x) for x in p.stdout.split()] == [600, 600, 600, 600]
    p, _ = run(fake, bash, show, READY_TIMEOUT="900", GW_READY_TIMEOUT="1200")
    assert [int(x) for x in p.stdout.split()] == [900, 900, 1200, 900]
