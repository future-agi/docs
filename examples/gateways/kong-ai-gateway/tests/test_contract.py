"""Contract test: protobuf captured from a real Kong 3.16.0.1 gateway, replayed at a Future AGI collector.

Needs a reachable collector: FI_BASE_URL, FI_API_KEY, FI_SECRET_KEY (skips otherwise). Storage assertions read
the local stack through `docker exec` (th8103-e2e-* containers, override with FI_CH_CONTAINER) and skip if absent.
Covers AC-02..AC-06: statistics-only vs payload spans, auth/project rejection, trace id preserved, no secrets in output.
"""
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

FIX = Path(__file__).resolve().parent.parent / "fixtures"
STATS = FIX / "kong-3.16.0.1-statistics-only.pb"
PAYLOADS = FIX / "kong-3.16.0.1-with-payloads.pb"

BASE = os.environ.get("FI_BASE_URL", "")
KEY = os.environ.get("FI_API_KEY", "")
SECRET = os.environ.get("FI_SECRET_KEY", "")
PROJECT = os.environ.get("FI_PROJECT_NAME", "th8103-rest-kong-ai-gateway")
CH = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")

pytestmark = pytest.mark.skipif(not (BASE and KEY and SECRET), reason="FI_BASE_URL/FI_API_KEY/FI_SECRET_KEY not set")


def build(path, project=PROJECT, trace_hex=None):
    """Load a captured Kong body; set project_name (or drop it) and give it fresh ids."""
    req = ExportTraceServiceRequest()
    req.ParseFromString(path.read_bytes())
    rs = req.resource_spans[0]
    attrs = [a for a in rs.resource.attributes if a.key not in ("project_name", "project_type")]
    if project:
        for k, v in (("project_name", project), ("project_type", "observe")):
            a = type(rs.resource.attributes[0])(key=k)
            a.value.string_value = v
            attrs.append(a)
    del rs.resource.attributes[:]
    rs.resource.attributes.extend(attrs)
    trace = bytes.fromhex(trace_hex or uuid.uuid4().hex)
    ids = {}
    for ss in rs.scope_spans:
        for sp in ss.spans:
            sp.trace_id = trace
            old = bytes(sp.span_id)
            ids.setdefault(old, os.urandom(8))
            sp.span_id = ids[old]
    for ss in rs.scope_spans:                       # keep parent links consistent; the root keeps its W3C parent
        for sp in ss.spans:
            if bytes(sp.parent_span_id) in ids:
                sp.parent_span_id = ids[bytes(sp.parent_span_id)]
    return req.SerializeToString(), trace.hex()


def post(body, key=KEY, secret=SECRET, headers=None):
    h = {"Content-Type": "application/x-protobuf"}
    if key:
        h["X-Api-Key"] = key
    if secret:
        h["X-Secret-Key"] = secret
    h.update(headers or {})
    return requests.post(BASE + "/v1/traces", data=body, headers=h, timeout=30)


def uuid_form(h):
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def stored(trace_hex, cols, wait=60):
    """Rows of the ClickHouse spans table for a trace (local stack only)."""
    sql = f"SELECT {cols} FROM spans FINAL WHERE trace_id='{uuid_form(trace_hex)}' ORDER BY start_time FORMAT JSONEachRow"
    end = time.time() + wait
    last = ""
    while time.time() < end:
        r = subprocess.run(["docker", "exec", CH, "clickhouse-client", "-q", sql], capture_output=True, text=True)
        if r.returncode == 127 or "No such container" in r.stderr:
            pytest.skip("local ClickHouse container not available")
        last = r.stdout
        if r.returncode == 0 and r.stdout.strip():
            import json
            return [json.loads(x) for x in r.stdout.splitlines()]
        time.sleep(3)
    pytest.fail(f"no stored rows for {trace_hex}: {last[:200]}")


def test_fixtures_are_kong_gen_ai_shape():
    req = ExportTraceServiceRequest()
    req.ParseFromString(STATS.read_bytes())
    names = {sp.name.split(" ")[0] for ss in req.resource_spans[0].scope_spans for sp in ss.spans}
    assert names == {"kong", "chat"}
    keys = {a.key for ss in req.resource_spans[0].scope_spans for sp in ss.spans for a in sp.attributes}
    assert {"gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens"} <= keys
    assert "gen_ai.input.messages" not in keys


def test_missing_project_name_is_rejected():
    body, _ = build(STATS, project=None)
    r = post(body)
    assert r.status_code == 400 and "project_name" in r.text


@pytest.mark.parametrize("key,secret", [("wrong", "wrong"), (KEY, "wrong"), ("", "")])
def test_bad_or_missing_keys_get_401_and_nothing_is_written(key, secret):
    body, trace = build(STATS)
    r = post(body, key=key, secret=secret)
    assert r.status_code == 401
    assert "wrong" not in r.text and SECRET not in r.text
    time.sleep(3)
    sql = f"SELECT count() FROM spans WHERE trace_id='{uuid_form(trace)}'"
    out = subprocess.run(["docker", "exec", CH, "clickhouse-client", "-q", sql], capture_output=True, text=True)
    if out.returncode == 0:
        assert out.stdout.strip() == "0"


def test_bearer_is_not_the_auth_scheme():
    body, _ = build(STATS)
    r = requests.post(BASE + "/v1/traces", data=body, headers={"Content-Type": "application/x-protobuf",
                                                              "Authorization": "Bearer " + KEY}, timeout=30)
    assert r.status_code == 401


def test_statistics_only_span_has_model_and_tokens_and_no_prompt():
    body, trace = build(STATS)
    assert post(body).status_code == 200
    rows = stored(trace, "name,observation_type,model,provider,prompt_tokens,completion_tokens,input,output,attributes_extra,parent_span_id")
    llm = next(r for r in rows if r["observation_type"] == "llm")
    assert llm["model"] == "gpt-6-luna" and llm["provider"] == "openai"
    assert llm["prompt_tokens"] > 0 and llm["completion_tokens"] > 0
    assert llm["input"] == "" and llm["output"] == ""
    assert "gen_ai.input.messages" not in llm["attributes_extra"]
    assert "FIXTURE-PROMPT-MARKER" not in str(rows)


def test_payload_span_stores_messages_and_stripped_variant_does_not():
    body, trace = build(PAYLOADS)
    assert post(body).status_code == 200
    rows = stored(trace, "name,observation_type,input,output,attributes_extra")
    assert "FIXTURE-PROMPT-MARKER" in str(rows)           # lands in attributes_extra (not promoted to input/output)
    body2, trace2 = build(STATS)
    assert post(body2).status_code == 200
    assert "FIXTURE-PROMPT-MARKER" not in str(stored(trace2, "name,input,output,attributes_extra,attrs_string"))


def test_w3c_trace_id_and_parent_are_preserved():
    caller_trace = uuid.uuid4().hex
    body, trace = build(STATS, trace_hex=caller_trace)
    assert trace == caller_trace
    assert post(body).status_code == 200
    rows = stored(caller_trace, "name,trace_id,parent_span_id")
    assert {r["trace_id"] for r in rows} == {uuid_form(caller_trace)}
    root = next(r for r in rows if r["name"] == "kong")
    assert root["parent_span_id"] == "b7ad6b7169203331"      # the caller's span id from traceparent survives


def test_stored_row_has_no_secret_values():
    body, trace = build(STATS)
    assert post(body).status_code == 200
    rows = stored(trace, "*")
    blob = str(rows)
    assert SECRET not in blob and KEY not in blob
