"""check_trace, wire_summary, wire_tap and the scan helper, without network or Docker."""
import gzip
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import check_trace
import pytest
import scan_local_stack
import wire_summary
import wire_tap
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


def span(trace, sid, name, parent="", kind="unknown", status="OK", inv="inv_1", **attrs):
    a = {"restate.invocation.id": inv} if name.startswith(check_trace.RESTATE_PREFIXES) else {}
    a.update(attrs)
    return {"trace_id": trace, "id": sid, "parent_span_id": parent, "name": name,
            "observation_type": kind, "status": status, "attrs_string": a}


def retried_invocation(trace="t1", inv="inv_1"):
    t = "W/{key}/ask"
    return [
        span(trace, "i", f"ingress {t}", inv=inv),
        span(trace, "s", f"invocation-start {t}", "i", inv=inv),
        span(trace, "a1", f"invocation-attempt {t}", "s", status="ERROR", inv=inv),
        span(trace, "l1", "ChatCompletion", "a1", kind="llm"),
        span(trace, "x1", "get_weather", "a1", kind="tool", status="ERROR"),
        span(trace, "a2", f"invocation-attempt {t}", "s", inv=inv),
        span(trace, "x2", "get_weather", "a2", kind="tool"),
        span(trace, "l2", "ChatCompletion", "a2", kind="llm"),
        span(trace, "e", f"invocation-end {t}", "s", inv=inv, **{"restate.invocation.result": "success"}),
    ]


def rules(spans, **kw):
    return {name: ok for name, ok, _ in check_trace.check(check_trace.summarize(spans), **kw)}


def test_check_trace_accepts_a_retried_invocation_with_one_copy_of_each_model_step():
    spans = retried_invocation() + retried_invocation("t2", "inv_2")
    got = rules(spans, invocations=2, model_steps=2)
    assert all(got.values()), got
    summary = check_trace.summarize(spans)["traces"]["t1"]
    assert (summary["attempts"], summary["attempts_error"], summary["tool_error"], summary["llm_ok"]) == (2, 1, 1, 2)


def test_check_trace_flags_a_model_step_emitted_again_on_replay():
    spans = retried_invocation()
    spans.append(span("t1", "l3", "ChatCompletion", "a2", kind="llm"))
    assert rules(spans, invocations=None, model_steps=2)["no-replay-duplicates"] is False


def test_check_trace_flags_orphans_and_split_invocations():
    spans = retried_invocation()
    spans.append(span("t1", "l9", "ChatCompletion", "nope", kind="llm"))
    spans.append(span("t9", "s9", "invocation-start W/{key}/ask", inv="inv_1"))
    got = rules(spans, invocations=1, model_steps=None)
    assert got["parent-is-attempt"] is False
    assert got["one-trace-per-invocation"] is False


def test_wire_summary_rules():
    good = {"content_encoding": None, "has_key_headers": True, "key_values_match": True, "status": 200,
            "body": {"resourceSpans": [{"resource": {"attributes": [
                {"key": "project_name", "value": {"stringValue": "p"}},
                {"key": "service.name", "value": {"stringValue": "Restate"}}]},
                "scopeSpans": [{"spans": [{"name": "invocation-start W/{key}/ask"}]}]}]}}
    _, r = wire_summary.summarize([good], "p")
    assert all(ok for _, ok, _ in r)
    bad = dict(good, content_encoding="gzip", key_values_match=False, status=401)
    _, r = wire_summary.summarize([bad], "other")
    assert {n for n, ok, _ in r if not ok} == {"uncompressed", "key-headers", "project-name", "accepted"}


@pytest.fixture
def tap(tmp_path, monkeypatch):
    monkeypatch.setenv("TAP_EXPECT_API_KEY", "key-a")
    monkeypatch.setenv("TAP_EXPECT_SECRET_KEY", "key-b")
    out = tmp_path / "wire.jsonl"
    server = ThreadingHTTPServer(("127.0.0.1", 0), wire_tap.make_handler(str(out), None, False))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", out
    server.shutdown()


def _payload():
    req = ExportTraceServiceRequest()
    sp = req.resource_spans.add().scope_spans.add().spans.add()
    sp.name = "invocation-start W/{key}/ask"
    sp.trace_id, sp.span_id = b"\x01" * 16, b"\x02" * 8
    return req.SerializeToString()


@pytest.mark.parametrize("gz", [False, True])
def test_wire_tap_records_header_names_and_value_match_but_never_values(tap, gz):
    url, out = tap
    body = gzip.compress(_payload()) if gz else _payload()
    headers = {"content-type": "application/x-protobuf", "X-Api-Key": "key-a", "X-Secret-Key": "key-b"}
    if gz:
        headers["content-encoding"] = "gzip"
    urllib.request.urlopen(urllib.request.Request(url + "/tracer/v1/traces", data=body, headers=headers))
    rec = json.loads(out.read_text().splitlines()[-1])
    assert rec["has_key_headers"] and rec["key_values_match"]
    assert rec["content_encoding"] == ("gzip" if gz else None)
    assert rec["body"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"].startswith("invocation-start")
    assert "key-a" not in out.read_text() and "key-b" not in out.read_text()


def test_wire_tap_value_mismatch_is_reported(tap):
    url, out = tap
    headers = {"content-type": "application/x-protobuf", "X-Api-Key": "wrong", "X-Secret-Key": "key-b"}
    urllib.request.urlopen(urllib.request.Request(url + "/v1/traces", data=_payload(), headers=headers))
    assert json.loads(out.read_text())["key_values_match"] is False


def test_scan_counts_plain_and_json_escaped_forms():
    blobs = {"spans": '{"a":"\\/Users\\/me x","b":"/Users/me"}', "traces": "nothing"}
    assert scan_local_stack.count(blobs, "/Users/me", False) == {"spans": 2}
    assert scan_local_stack.count(blobs, "/USERS/ME", True) == {"spans": 2}
    assert scan_local_stack.count(blobs, "absent", False) == {}
