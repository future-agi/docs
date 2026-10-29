"""Runs the shipped collector config in Docker on spans recorded from a real LobeHub v2.2.19 server.

The fixture (tests/fixtures/lobehub-v2.2.19-export.json) is LobeHub's own OTLP export of three agent runs
(a web-app chat in Gateway Mode with a tool call, a POST /api/agent run with a tool call, and a run whose
model does not exist) plus three unrelated traces (a page load, a tRPC query, the gateway start call),
with host names, client IPs and user agents replaced. The collector forwards to a local HTTP sink that
records what Future AGI would receive.

Skipped when Docker is not available. Set OTELCOL_IMAGE to test another collector build.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import uuid

import pytest

EXAMPLE = pathlib.Path(__file__).resolve().parents[1]
CONFIG = EXAMPLE / "otelcol" / "otelcol.yaml"
FIXTURE = EXAMPLE / "tests" / "fixtures" / "lobehub-v2.2.19-export.json"
IMAGE = os.environ.get("OTELCOL_IMAGE", "otel/opentelemetry-collector-contrib:0.162.0")
SINK_HOST = os.environ.get("SINK_HOST", "127.0.0.1")  # Linux Docker: set 0.0.0.0

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")

trace_pb2 = pytest.importorskip("opentelemetry.proto.collector.trace.v1.trace_service_pb2")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Sink(http.server.ThreadingHTTPServer):
    def __init__(self, port):
        self.requests = []

        sink = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                sink.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.end_headers()
                self.wfile.write(trace_pb2.ExportTraceServiceResponse().SerializeToString())

            def log_message(self, *a):
                pass

        super().__init__((SINK_HOST, port), Handler)


def _run_collector(capture: str):
    sink_port, otlp_port = _free_port(), _free_port()
    sink = Sink(sink_port)
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    name = f"lobehub-otelcol-test-{uuid.uuid4().hex[:8]}"
    cmd = ["docker", "run", "-d", "--rm", "--name", name, "--memory", "256m",
           "--add-host", "host.docker.internal:host-gateway",
           "-p", f"127.0.0.1:{otlp_port}:4318",
           "-v", f"{CONFIG}:/etc/otelcol/config.yaml:ro",
           "-e", f"FI_TRACES_URL=http://host.docker.internal:{sink_port}/v1/traces",
           "-e", "FI_PROJECT_NAME=lobehub-test",
           "-e", f"FI_CAPTURE_CONTENT={capture}",
           IMAGE, "--config=/etc/otelcol/config.yaml"]
    subprocess.run(cmd, check=True, capture_output=True)
    return name, sink, otlp_port


def _post(port, path, payload, headers):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    for _ in range(40):
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except OSError:
            time.sleep(0.5)
    raise AssertionError(f"collector did not accept {path}")


def _decode(sink):
    spans, resources = [], []
    for r in sink.requests:
        msg = trace_pb2.ExportTraceServiceRequest()
        msg.ParseFromString(r["body"])
        for rs in msg.resource_spans:
            res = {a.key: a.value for a in rs.resource.attributes}
            resources.append(res)
            for ss in rs.scope_spans:
                for s in ss.spans:
                    spans.append({
                        "scope": ss.scope.name, "name": s.name, "trace": s.trace_id.hex(),
                        "id": s.span_id.hex(), "parent": s.parent_span_id.hex(),
                        "status": s.status.code, "status_message": s.status.message,
                        "attrs": {a.key: a.value for a in s.attributes},
                        "events": [{a.key: a.value for a in e.attributes} for e in s.events],
                    })
    return spans, resources


def _sv(v):
    return v.string_value if v.HasField("string_value") else (v.int_value if v.HasField("int_value") else v)


@pytest.fixture(scope="module", params=["false", "true"], ids=["content-off", "content-on"])
def exported(request):
    name, sink, port = _run_collector(request.param)
    try:
        payload = json.loads(FIXTURE.read_text())
        assert _post(port, "/v1/traces", payload, {"X-Api-Key": "test-key", "X-Secret-Key": "test-secret"}) == 200
        metrics = {"resourceMetrics": [{"resource": {"attributes": []}, "scopeMetrics": [{"scope": {"name": "m"},
                   "metrics": [{"name": "x", "sum": {"dataPoints": [{"asInt": "1", "timeUnixNano": "1"}],
                                                       "aggregationTemporality": 2, "isMonotonic": True}}]}]}]}
        metrics_status = _post(port, "/v1/metrics", metrics, {})
        deadline = time.time() + 30
        while time.time() < deadline and not sink.requests:
            time.sleep(0.5)
        time.sleep(3)  # let the batch processor flush everything
        spans, resources = _decode(sink)
        yield {"capture": request.param, "sink": sink, "spans": spans, "resources": resources,
               "metrics_status": metrics_status}
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        sink.shutdown()


def _raw_agent_spans():
    raw = json.loads(FIXTURE.read_text())
    out = []
    for rs in raw["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for s in ss["spans"]:
                out.append((ss["scope"]["name"], s))
    return out


def test_transport_uncompressed_proto_to_traces_path_with_callers_keys(exported):
    reqs = exported["sink"].requests
    assert reqs, "nothing reached the sink"
    for r in reqs:
        h = {k.lower(): v for k, v in r["headers"].items()}
        assert r["path"] == "/v1/traces"
        assert h["content-type"] == "application/x-protobuf"
        assert "content-encoding" not in h or h["content-encoding"] == "identity"
        assert h["x-api-key"] == "test-key" and h["x-secret-key"] == "test-secret"


def test_metrics_are_accepted_and_not_forwarded(exported):
    assert exported["metrics_status"] == 200
    assert all(r["path"] == "/v1/traces" for r in exported["sink"].requests)


def test_only_agent_runtime_and_entry_spans_kept(exported):
    spans = exported["spans"]
    kept_raw = [s for sc, s in _raw_agent_spans() if sc == "@lobechat/agent-runtime"]
    assert {s["name"] for s in spans if s["scope"] == "@lobechat/agent-runtime"} == {s["name"] for s in kept_raw}
    others = {(s["scope"], s["name"]) for s in spans if s["scope"] != "@lobechat/agent-runtime"}
    assert others == {("trpc-server", "tRPC MUTATION aiAgent.execAgent"),
                      ("next.js", "executing api route (app) /api/agent/[[...route]]")}
    assert len([s for s in spans if s["scope"] == "@lobechat/agent-runtime"]) == len(kept_raw)


def test_one_root_per_run_and_no_orphans(exported):
    spans = exported["spans"]
    by_trace = {}
    for s in spans:
        by_trace.setdefault(s["trace"], []).append(s)
    for trace, ss in by_trace.items():
        ids = {s["id"] for s in ss}
        roots = [s for s in ss if s["parent"] in ("", "0000000000000000")]
        assert len(roots) == 1, (trace, [r["name"] for r in roots])
        assert all(s["parent"] in ids for s in ss if s not in roots)


def test_kinds_session_tool_and_tokens(exported):
    for s in exported["spans"]:
        a = s["attrs"]
        op = _sv(a["gen_ai.operation.name"]) if "gen_ai.operation.name" in a else None
        if op == "invoke_agent":
            assert _sv(a["gen_ai.span.kind"]) == "AGENT"
            assert not [k for k in a if k.startswith("gen_ai.usage.")]
        elif op is None:
            assert _sv(a["fi.span.kind"]) == "CHAIN"
        if op == "execute_tool":
            assert _sv(a["tool.name"]).startswith("ordertools/")
        if op in ("chat", "invoke_agent"):
            assert _sv(a["session.id"]) == _sv(a["gen_ai.conversation.id"])
    chats = [s for s in exported["spans"] if s["name"].startswith("chat ") and s["status"] != 2]
    assert chats and all("gen_ai.usage.input_tokens" in s["attrs"] for s in chats)
    completed = [s for s in exported["spans"] if "lobehub.agent.usage.input_tokens" in s["attrs"]]
    assert completed


def test_errors(exported):
    spans = exported["spans"]
    err_chat = [s for s in spans if s["name"].startswith("chat ") and s["status"] == 2]
    err_agent = [s for s in spans if s["name"].startswith("invoke_agent") and s["status"] == 2]
    assert err_chat and err_agent
    if exported["capture"] == "false":
        assert all(s["status_message"] == "error" for s in spans if s["status"] == 2)
        assert not [e for s in spans for e in s["events"] if "exception.message" in e or "exception.stacktrace" in e]
    else:
        assert any("unknown provider" in e.get("exception.message", _Str()).string_value
                   for s in err_chat for e in s["events"])


class _Str:
    string_value = ""


def test_resource_is_clean_and_project_set(exported):
    for res in exported["resources"]:
        assert res["project_name"].string_value == "lobehub-test"
        assert res["project_type"].string_value == "observe"
        assert not [k for k in res if k.split(".")[0] in ("host", "os", "process", "container")]


def test_no_request_details_on_kept_spans(exported):
    blob = json.dumps([{k: str(v) for k, v in s["attrs"].items()} for s in exported["spans"]])
    for needle in ("192.0.2.", "Mozilla", "host.docker.internal", "http.url", "url.full", "http.user_agent"):
        assert needle not in blob, needle
