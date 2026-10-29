"""The E2E helpers fail when they should (synthetic inputs, no network)."""
import argparse

import check_trace
import wire_summary


def span(sid, name, kind, parent="", status="UNSET", trace="t1", **extra):
    base = {"trace_id": trace, "id": sid, "parent_span_id": parent, "name": name, "observation_type": kind,
            "status": status, "status_message": "", "model": "", "provider": "", "prompt_tokens": 0,
            "completion_tokens": 0, "session": "s1", "input_length": 0, "output_length": 0, "attrs_string": {}}
    base.update(extra)
    return base


GOOD = [
    span("r", "weather-agent", "chain"),
    span("a", "agent_node", "agent", "r"),
    span("l", "chat_model", "llm", "a", model="m", provider="openai", prompt_tokens=10, completion_tokens=2),
    span("t", "get_weather", "tool", "r", status="ERROR", status_message="error"),
]


def args(**kw):
    base = {"traces": None, "tool_error": False, "failed_run": False, "content_off": False}
    base.update(kw)
    return argparse.Namespace(**base)


def results(spans, **kw):
    return {name: ok for name, ok, _ in check_trace.rules(spans, args(**kw))}


def test_good_trace_passes_every_rule():
    assert all(results(GOOD, traces=1, tool_error=True, content_off=True).values())


def test_llm_outside_an_agent_span_fails_hierarchy():
    bad = GOOD[:2] + [dict(GOOD[2], parent_span_id="r")] + GOOD[3:]
    assert results(bad)["hierarchy"] is False


def test_unknown_kinds_fail_one_root_and_llm_details():
    unknown = [dict(s, observation_type="unknown") for s in GOOD]
    r = results(unknown)
    assert r["one-root"] is False and r["llm-details"] is False


def test_stored_input_or_raw_error_text_fails_content_off():
    assert results([dict(GOOD[0], input_length=12)] + GOOD[1:], content_off=True)["content-off"] is False
    assert results(GOOD[:3] + [dict(GOOD[3], status_message="no station for x")], content_off=True)["content-off"] is False
    assert results([dict(GOOD[0], attrs_string={"user.id": "u"})] + GOOD[1:], content_off=True)["content-off"] is False


def test_wire_summary_flags_a_forwarded_bearer_and_gzip():
    rec = {"header_names": ["content-type", "x-api-key", "x-secret-key"], "has_key_headers": True, "status": 200,
           "content_encoding": None,
           "body": {"resourceSpans": [{"resource": {"attributes": [{"key": "project_name", "value": {"stringValue": "p"}}]},
                                       "scopeSpans": []}]}}
    _, ok = wire_summary.summarize([rec], "p")
    assert all(passed for _, passed, _ in ok)
    bearer = dict(rec, header_names=rec["header_names"] + ["authorization"], content_encoding="gzip")
    _, bad = wire_summary.summarize([bearer], "p")
    failed = {name for name, passed, _ in bad if not passed}
    assert failed == {"no-bearer", "uncompressed"}
