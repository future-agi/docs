"""run_e2e.sh step 7, the gateway's own OTLP/gRPC export: it must fail unless the spans were stored.

Hermetic. A stub stands in for the gateway binary (STANDIN) and a stub verifier stands in for the
read-back from Future AGI, so no network, npm install or Future AGI is needed. What the real gateway
does with its OTLP endpoint is pinned in test_gateway_otlp_real.py (opt-in).
"""
import json
import os
import socket
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FI_KEY = "fi-step7-api-key-value"
FI_SECRET = "fi-step7-secret-key-value"
PROJECT = "helicone-step7"

STUB_GATEWAY = textwrap.dedent(
    """\
    #!{python}
    # STANDIN for the ai-gateway binary: serves /health and /ai/chat/completions and records how it was started.
    import json, os, re, signal, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    state = os.environ["STUB_STATE_DIR"]
    cfg = open(sys.argv[sys.argv.index("-c") + 1]).read()
    headers = dict(kv.split("=", 1) for kv in os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "").split(",") if "=" in kv)
    with open(os.path.join(state, "gateway-start.json"), "w") as f:
        json.dump({{
            "config": cfg,
            "header_names": sorted(headers),
            "api_key_matches": headers.get("x-api-key") == os.environ["FI_API_KEY"],
            "secret_key_matches": headers.get("x-secret-key") == os.environ["FI_SECRET_KEY"],
            "resource_attributes": os.environ.get("OTEL_RESOURCE_ATTRIBUTES", ""),
        }}, f)

    def stop(*_):
        open(os.path.join(state, "gateway-stopped"), "w").close()
        os._exit(0)

    signal.signal(signal.SIGTERM, stop)
    status = int(os.environ.get("STUB_CHAT_STATUS", "200"))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(200 if self.path == "/health" else 404, {{}})

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self._send(status, {{"choices": [{{"message": {{"role": "assistant", "content": "hi"}}}}]}})

    HTTPServer(("127.0.0.1", int(re.search(r"port: (\\d+)", cfg).group(1))), H).serve_forever()
    """
)

STUB_VERIFY = textwrap.dedent(
    """\
    # STANDIN for the read-back from Future AGI (FI_VERIFY): records its arguments and whether the gateway
    # had already been stopped (its shutdown is what flushes the spans), then exits with STUB_VERIFY_EXIT.
    import argparse, json, os, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--project"); ap.add_argument("--wait", type=int); ap.add_argument("--min-spans", type=int)
    a = ap.parse_args()
    state = os.environ["STUB_STATE_DIR"]
    with open(os.path.join(state, "verify.json"), "w") as f:
        json.dump({"project": a.project, "wait": a.wait, "min_spans": a.min_spans,
                   "gateway_stopped_first": os.path.exists(os.path.join(state, "gateway-stopped"))}, f)
    code = int(os.environ.get("STUB_VERIFY_EXIT", "1"))
    print("PASS: traces=1 spans=12" if code == 0 else f"FAIL: project {a.project!r} does not exist (nothing was ingested)")
    sys.exit(code)
    """
)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def step7(tmp_path):
    work, state = tmp_path / "work", tmp_path / "state"
    work.mkdir()
    state.mkdir()
    gateway = tmp_path / "ai-gateway"
    gateway.write_text(STUB_GATEWAY.format(python=sys.executable))
    gateway.chmod(gateway.stat().st_mode | stat.S_IXUSR)
    (work / "gw-bin.path").write_text(f"{gateway}\n")
    verify = tmp_path / "verify.py"
    verify.write_text(STUB_VERIFY)

    def _run(**overrides):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OTEL_", "STUB_", "E2E_", "HELICONE_"))}
        env.update(
            E2E_UPSTREAM_URL="http://127.0.0.1:9",
            E2E_UPSTREAM_KEY="upstream-key-not-used",
            E2E_UPSTREAM_MODEL="stub-model",
            FI_API_KEY=FI_KEY,
            FI_SECRET_KEY=FI_SECRET,
            FI_PROJECT_NAME=PROJECT,
            FI_GRPC_ENDPOINT="http://127.0.0.1:1",  # never contacted: the stub gateway exports nothing
            FI_VERIFY=str(verify),
            PYTHON=sys.executable,
            E2E_WORKDIR=str(work),
            E2E_STEPS="7",
            GATEWAY_PORT=str(_free_port()),
            STEP7_SETTLE="0",
            STUB_STATE_DIR=str(state),
        )
        for k, v in overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        proc = subprocess.run(
            ["bash", str(ROOT / "run_e2e.sh")], env=env, capture_output=True, text=True, timeout=60
        )
        out = proc.stdout + proc.stderr
        assert FI_KEY not in out and FI_SECRET not in out
        return proc, out, state

    return _run


def _read(state, name):
    p = state / name
    return json.loads(p.read_text()) if p.exists() else None


def test_endpoint_without_scheme_is_refused_before_anything_runs(step7):
    # The sweep passed "localhost:14337": the real gateway then exports nothing and logs no error.
    proc, out, state = step7(FI_GRPC_ENDPOINT="localhost:14337")
    assert proc.returncode != 0
    assert "must include the scheme" in out
    assert _read(state, "gateway-start.json") is None


def test_step7_needs_a_read_back(step7):
    proc, out, state = step7(FI_VERIFY=None)
    assert proc.returncode != 0
    assert "FI_VERIFY" in out
    assert _read(state, "gateway-start.json") is None


def test_step7_fails_when_nothing_is_stored(step7):
    proc, out, state = step7(STUB_VERIFY_EXIT="1")
    assert proc.returncode != 0
    assert f"FAIL step 7: no spans stored in project {PROJECT}-gateway-otlp" in out
    assert "PASS step 7" not in out
    verify = _read(state, "verify.json")
    assert verify["project"] == f"{PROJECT}-gateway-otlp"
    assert verify["min_spans"] >= 1
    assert verify["gateway_stopped_first"] is True


def test_step7_passes_only_on_a_stored_read_back(step7):
    proc, out, state = step7(STUB_VERIFY_EXIT="0")
    assert proc.returncode == 0, out
    assert f"PASS step 7: spans stored in project {PROJECT}-gateway-otlp" in out
    start = _read(state, "gateway-start.json")
    assert 'exporter: "otlp"' in start["config"]
    assert 'otlp-endpoint: "http://127.0.0.1:1"' in start["config"]
    assert start["header_names"] == ["x-api-key", "x-secret-key"]
    assert start["api_key_matches"] and start["secret_key_matches"]
    attrs = dict(kv.split("=", 1) for kv in start["resource_attributes"].split(","))
    assert attrs == {"project_name": f"{PROJECT}-gateway-otlp", "project_type": "observe"}
    assert _read(state, "verify.json")["gateway_stopped_first"] is True


def test_step7_fails_when_the_gateway_request_fails(step7):
    proc, out, state = step7(STUB_CHAT_STATUS="502", STUB_VERIFY_EXIT="0")
    assert proc.returncode != 0
    assert "returned HTTP 502" in out
    assert _read(state, "verify.json") is None


def test_step7_is_reported_as_skipped_without_an_endpoint(step7):
    proc, out, state = step7(FI_GRPC_ENDPOINT=None, FI_VERIFY=None)
    assert proc.returncode == 0, out
    assert "== 7. skipped" in out
    assert "PASS step 7" not in out
    assert _read(state, "gateway-start.json") is None
