"""Recorded span tree from a real Swiftide 0.33.0 run (content capture off), checked offline and,
with RUN_FI_REPLAY=1, replayed into a Future AGI.

  pip install -r tests/replay/requirements.txt
  pytest tests/replay -q                                   # offline checks
  RUN_FI_REPLAY=1 FI_BASE_URL=http://localhost:<port> FI_API_KEY=... FI_SECRET_KEY=... \
    [VERIFY=/path/to/fi_verify.py] pytest tests/replay -q  # + replay (and read-back with VERIFY)

The fixture was recorded by tools/wire_tap.py during `run_e2e.sh main` and built with
tools/make_fixture.py: three agent queries (an answer, a failed tool call, an unknown model).
"""
import base64
import copy
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent.parent
FIXTURE = HERE.parent / "fixtures" / "swiftide-0.33.0-content-off.json"
ALLOWED = {"busy_ns", "idle_ns", "step_count", "target"}
sys.path.insert(0, str(EXAMPLE / "tools"))

import check_trace  # noqa: E402


def load() -> dict:
    return json.loads(FIXTURE.read_text())


def spans(doc: dict):
    for rs in doc["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            yield rs, ss["spans"]


def rows(doc: dict) -> list[dict]:
    out = []
    for _, ss in spans(doc):
        for s in ss:
            status = s.get("status", {}).get("code", "")
            out.append({
                "trace_id": s["traceId"], "id": s["spanId"], "parent_span_id": s.get("parentSpanId", ""),
                "name": s["name"], "status": "ERROR" if status == "STATUS_CODE_ERROR" else "UNSET",
            })
    return out


def test_tree_matches_the_live_run():
    args = type("A", (), {"traces": 3, "ok": 1, "model_errors": 1, "tool_errors": 1})()
    results = check_trace.check(rows(load()), args)
    assert all(passed for _, passed, _ in results), results


def test_fixture_is_content_free():
    doc = load()
    for rs, ss in spans(doc):
        keys = {kv["key"] for kv in rs["resource"]["attributes"]}
        assert keys <= {"project_name", "project_type", "service.name", "telemetry.sdk.language",
                        "telemetry.sdk.name", "telemetry.sdk.version"}, keys
        for s in ss:
            assert not s.get("events"), s["name"]
            assert {a["key"] for a in s.get("attributes", [])} <= ALLOWED, s["name"]
            message = s.get("status", {}).get("message")
            assert message in (None, "", "error"), message


def fresh_copy(doc: dict, project: str) -> dict:
    """New trace and span ids, timestamps moved to now, project renamed."""
    doc = copy.deepcopy(doc)
    trace_ids, span_ids = {}, {}
    starts = [int(s["startTimeUnixNano"]) for _, ss in spans(doc) for s in ss]
    shift = time.time_ns() - max(starts) - 5_000_000_000

    def new_id(table, old, size):
        if old not in table:
            table[old] = base64.b64encode(secrets.token_bytes(size)).decode()
        return table[old]

    for rs, ss in spans(doc):
        for kv in rs["resource"]["attributes"]:
            if kv["key"] == "project_name":
                kv["value"] = {"stringValue": project}
        for s in ss:
            s["traceId"] = new_id(trace_ids, s["traceId"], 16)
            s["spanId"] = new_id(span_ids, s["spanId"], 8)
            if s.get("parentSpanId"):
                s["parentSpanId"] = new_id(span_ids, s["parentSpanId"], 8)
            s["startTimeUnixNano"] = str(int(s["startTimeUnixNano"]) + shift)
            s["endTimeUnixNano"] = str(int(s["endTimeUnixNano"]) + shift)
    return doc


@pytest.mark.skipif(os.environ.get("RUN_FI_REPLAY") != "1", reason="set RUN_FI_REPLAY=1 to post to a Future AGI")
def test_replay_into_future_agi():
    from google.protobuf.json_format import ParseDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    project = os.environ.get("REPLAY_PROJECT", f"swiftide-fixture-replay-{int(time.time())}")
    body = ParseDict(fresh_copy(load(), project), ExportTraceServiceRequest()).SerializeToString()
    url = os.environ["FI_BASE_URL"].rstrip("/") + "/tracer/v1/traces"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/x-protobuf",
        "X-Api-Key": os.environ["FI_API_KEY"],
        "X-Secret-Key": os.environ["FI_SECRET_KEY"],
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        assert resp.status == 200
    verify = os.environ.get("VERIFY")
    if not verify:
        return
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "spans.json"
        n = sum(len(ss) for _, ss in spans(load()))
        subprocess.run([sys.executable, verify, "--project", project, "--wait", "120", "--min-spans", str(n),
                        "--json", str(out)], check=True)
        args = type("A", (), {"traces": 3, "ok": 1, "model_errors": 1, "tool_errors": 1})()
        results = check_trace.check(json.loads(out.read_text()), args)
        assert all(passed for _, passed, _ in results), results
