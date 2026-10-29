"""Contract test: OTLP bodies captured from a real Gravitee 4.12.23 Gateway, replayed at a Future AGI collector.

Needs a reachable collector: FI_BASE_URL, FI_API_KEY, FI_SECRET_KEY (skips otherwise). Storage assertions read
the local stack through `docker exec` (container th8103-e2e-clickhouse-1, override with FI_CH_CONTAINER) and skip
if it is absent. Covers: the direct export is rejected (no project_name), the Collector's fix is accepted, gzip and
bad credentials are rejected, and the caller's W3C trace id and parent survive.
"""
import gzip
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

FIX = Path(__file__).resolve().parent.parent / "fixtures"
BASE = os.environ.get("FI_BASE_URL", "")
KEY = os.environ.get("FI_API_KEY", "")
SECRET = os.environ.get("FI_SECRET_KEY", "")
PROJECT = os.environ.get("FI_PROJECT_NAME", "gravitee-fi-e2e")
CH = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")

pytestmark = pytest.mark.skipif(not (BASE and KEY and SECRET), reason="FI_BASE_URL/FI_API_KEY/FI_SECRET_KEY not set")


def build(name, project=PROJECT, trace_hex=None):
    """Load a captured body; optionally do what otelcol.yaml does (upsert project_name); fresh ids."""
    req = ExportTraceServiceRequest()
    req.ParseFromString((FIX / name).read_bytes())
    trace = bytes.fromhex(trace_hex or uuid.uuid4().hex)
    ids = {}
    for rs in req.resource_spans:
        if project:
            kept = [a for a in rs.resource.attributes if a.key not in ("project_name", "project_type")]
            for k, v in (("project_name", project), ("project_type", "observe")):
                a = type(rs.resource.attributes[0])(key=k)
                a.value.string_value = v
                kept.append(a)
            del rs.resource.attributes[:]
            rs.resource.attributes.extend(kept)
        for ss in rs.scope_spans:
            for sp in ss.spans:
                sp.trace_id = trace
                ids.setdefault(bytes(sp.span_id), os.urandom(8))
                sp.span_id = ids[bytes(sp.span_id)]
    for rs in req.resource_spans:          # keep parent links; the root keeps its W3C (caller) parent
        for ss in rs.scope_spans:
            for sp in ss.spans:
                if bytes(sp.parent_span_id) in ids:
                    sp.parent_span_id = ids[bytes(sp.parent_span_id)]
    return req.SerializeToString(), trace.hex()


def post(body, key=KEY, secret=SECRET, headers=None, path="/tracer/v1/traces"):
    h = {"Content-Type": "application/x-protobuf"}
    if key:
        h["X-Api-Key"] = key
    if secret:
        h["X-Secret-Key"] = secret
    h.update(headers or {})
    return requests.post(BASE.rstrip("/") + path, data=body, headers=h, timeout=30)


def uuid_form(h):
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def stored(trace_hex, wait=60):
    sql = (f"SELECT name, parent_span_id, status FROM spans FINAL WHERE trace_id='{uuid_form(trace_hex)}' "
           "FORMAT JSONEachRow")
    end = time.time() + wait
    while True:
        r = subprocess.run(["docker", "exec", CH, "clickhouse-client", "-q", sql], capture_output=True, text=True)
        if r.returncode == 127 or "No such container" in r.stderr or "Cannot connect to the Docker" in r.stderr:
            pytest.skip("local ClickHouse container not available")
        rows = [__import__("json").loads(x) for x in r.stdout.splitlines() if x.strip()]
        if rows or time.time() > end:
            return rows
        time.sleep(3)


def test_direct_export_is_rejected_without_project_name():
    body, trace = build("gravitee-4.12.23-extra-attributes.pb", project=None)   # carries project.name only
    r = post(body)
    assert r.status_code == 400, r.text[:200]
    assert "project_name" in r.text
    assert stored(trace, wait=5) == []


def test_collector_fix_is_accepted_and_keeps_the_callers_trace():
    req = ExportTraceServiceRequest()
    req.ParseFromString((FIX / "gravitee-4.12.23-content-off.pb").read_bytes())
    caller = [bytes(s.parent_span_id).hex() for rs in req.resource_spans for ss in rs.scope_spans for s in ss.spans
              if s.kind == s.SPAN_KIND_SERVER][0]
    body, trace = build("gravitee-4.12.23-content-off.pb")
    r = post(body)
    assert r.status_code == 200, r.text[:200]
    rows = stored(trace)
    assert rows, "accepted but not stored"
    names = {x["name"] for x in rows}
    assert "POST /fi-echo" in names and "endpoint-invoker" in names
    root = [x for x in rows if x["name"] == "POST /fi-echo"][0]
    assert root["parent_span_id"].replace("-", "").endswith(caller)


def test_errors_are_stored_as_error():
    body, trace = build("gravitee-4.12.23-backend-down.pb")
    assert post(body).status_code == 200
    rows = stored(trace)
    assert any(x["name"] == "GET /fi-down" and str(x["status"]).upper() == "ERROR" for x in rows), rows


def test_gzip_body_is_rejected():
    body, trace = build("gravitee-4.12.23-content-off.pb")
    r = post(gzip.compress(body), headers={"Content-Encoding": "gzip"})
    assert r.status_code != 200
    assert stored(trace, wait=5) == []


@pytest.mark.parametrize("key,secret,extra", [
    ("wrong", "wrong", None),
    ("", "", {"Authorization": "Bearer something"}),
])
def test_bad_credentials_are_rejected(key, secret, extra):
    body, trace = build("gravitee-4.12.23-content-off.pb")
    r = post(body, key=key, secret=secret, headers=extra)
    assert r.status_code == 401
    assert stored(trace, wait=5) == []


def test_url_with_v1_traces_appended_twice_is_not_a_traces_route():
    body, trace = build("gravitee-4.12.23-content-off.pb")
    r = post(body, path="/tracer/v1/traces/v1/traces")   # what Gravitee sends if the endpoint ends in /v1/traces
    assert r.status_code in (404, 405)
    assert stored(trace, wait=5) == []
