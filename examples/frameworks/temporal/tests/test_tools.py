"""The checking tools in tools/, on small synthetic data (no server, no Docker, no network)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import check_trace  # noqa: E402
import marker_locations  # noqa: E402
import scan_local_stack  # noqa: E402
import wire_check  # noqa: E402

WF = "wf-1"


def span(sid, name, parent=None, kind="unknown", status="OK", trace="t1", **attrs):
    return {"trace_id": trace, "id": sid, "parent_span_id": parent or "", "name": name, "observation_type": kind,
            "status": status, "attrs_string": {"session.id": WF, **attrs}}


def happy():
    return [
        span("1", "StartWorkflow:W"),
        span("2", "RunWorkflow:W", "1"),
        span("3", "StartActivity:llm_plan", "2"),
        span("4", "RunActivity:llm_plan", "3"),
        span("5", "ChatCompletion", "4", "llm"),
        span("6", "StartActivity:get_weather", "2"),
        span("7", "RunActivity:get_weather", "6"),
        span("8", "get_weather", "7", "tool"),
    ]


def rules(spans, **kw):
    _, result = check_trace.check(spans, kw.get("expect", {}), kw.get("errors", {}), kw.get("start_workflow", True), kw.get("llm"))
    return {name: ok for name, ok, _ in result}


def test_check_trace_accepts_the_expected_hierarchy():
    assert all(rules(happy(), llm=1, expect={"RunActivity:get_weather": 1}).values())


def test_check_trace_rejects_a_model_span_that_lost_its_activity_parent():
    spans = happy()
    spans[4]["parent_span_id"] = "2"  # ChatCompletion directly under RunWorkflow
    assert rules(spans)["hierarchy"] is False


def test_check_trace_rejects_a_second_trace_and_a_second_root():
    spans = happy() + [span("9", "ChatCompletion", None, "llm", trace="t2")]
    result = rules(spans)
    assert result["one-trace"] is False and result["roots"] is False


def test_check_trace_counts_attempts_and_errors():
    spans = happy() + [span("10", "RunActivity:get_weather", "6", status="ERROR")]
    result = rules(spans, expect={"RunActivity:get_weather": 2}, errors={"RunActivity:get_weather": 1})
    assert all(result.values())
    assert rules(spans, expect={"RunActivity:get_weather": 1})["expect RunActivity:get_weather"] is False


def test_check_trace_selects_a_workflow_and_ignores_prefixes():
    spans = happy() + [span("11", "HandleSignal:approve", trace="t2")]
    other = [dict(s, attrs_string={"session.id": "wf-2"}) for s in happy()]
    assert len(check_trace.workflow_spans(spans + other, WF)) == 9
    assert len(check_trace.workflow_spans(spans + other, WF, ("HandleSignal",))) == 8
    assert len(check_trace.workflow_spans(spans + other, None)) == 17


def test_check_trace_without_a_start_workflow_span_expects_the_workflow_as_root():
    spans = happy()[1:]
    assert rules(spans, start_workflow=False)["roots"] is True
    assert rules(spans)["roots"] is False


def wire_line(spans, status=200, encoding=None, project="p"):
    return {
        "content_encoding": encoding, "has_key_headers": True, "key_values_match": True, "status": status,
        "body": {"resourceSpans": [{
            "resource": {"attributes": [{"key": "project_name", "value": {"stringValue": project}}]},
            "scopeSpans": [{"spans": [{"name": n, "traceId": "t", "spanId": i} for i, n in spans]}],
        }]},
    }


def wire_rules(lines, **kw):
    _, result = wire_check.check(lines, kw.get("project"), kw.get("expect", {}), kw.get("allow_duplicates", False), kw.get("allow_empty", False), kw.get("total"))
    return {name: ok for name, ok, _ in result}


def test_wire_check_passes_a_clean_capture():
    result = wire_rules([wire_line([("1", "RunWorkflow:W"), ("2", "StartActivity:a")])], project="p", expect={"RunWorkflow:W": 1}, total=2)
    assert all(result.values())


def test_wire_check_catches_a_span_sent_twice_gzip_and_a_rejected_request():
    twice = wire_rules([wire_line([("1", "RunWorkflow:W")]), wire_line([("1", "RunWorkflow:W")])])
    assert twice["exactly-once"] is False
    assert wire_rules([wire_line([("1", "x")], encoding="gzip")])["uncompressed"] is False
    assert wire_rules([wire_line([("1", "x")], status=400)])["accepted"] is False
    assert wire_rules([wire_line([("1", "x")], project="other")], project="p")["project-name"] is False


def test_wire_check_empty_capture_needs_allow_empty():
    assert wire_rules([], total=0)["key-headers"] is False
    assert all(wire_rules([], allow_empty=True, total=0).values())
    assert wire_rules([], allow_empty=True, total=1)["total"] is False


def test_scan_needles_match_plain_escaped_and_json_forms():
    blobs = {"clickhouse.spans": '{"input": "a\\/b\\/home\\/user", "status": "tmpmarker1"}', "postgres.t": "nothing"}
    assert scan_local_stack.count(blobs, "tmpmarker1", False) == {"clickhouse.spans": 1}
    assert scan_local_stack.count(blobs, "/b/home/user", False) == {"clickhouse.spans": 1}
    assert scan_local_stack.count(blobs, "TMPMARKER1", False) == {}
    assert scan_local_stack.count(blobs, "TMPMARKER1", True) == {"clickhouse.spans": 1}


def test_marker_locations_names_spans_and_fields_not_content():
    spans = [
        {"name": "ChatCompletion", "status_message": "", "input_head": "", "output_head": "", "attrs_string": {"gen_ai.input.messages.1.message.content": "see tmpmark9"}},
        {"name": "RunActivity:a", "status_message": "TimeoutError: tmpmark9", "input_head": "", "output_head": "", "attrs_string": {}},
        {"name": "other", "status_message": "", "input_head": "", "output_head": "", "attrs_string": {"k": "v"}},
    ]
    assert marker_locations.locations(spans, "tmpmark9") == {
        "ChatCompletion": ["gen_ai.input.messages.1.message.content"],
        "RunActivity:a": ["status_message"],
    }


@pytest.mark.parametrize("script", ["worker.py", "starter.py", "tracing.py", "activities.py", "workflows.py"])
def test_example_files_parse(script):
    import ast

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", script)
    ast.parse(open(path).read())


def test_recorded_retry_trace_from_temporalio_1_34_0_passes_the_checks():
    """A real trace as Future AGI stored it (sanitized: names, ids, parents, status and Temporal ids only)."""
    import json

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "temporal_1.34.0_retry_spans.json")
    spans = check_trace.workflow_spans(json.load(open(path)), "wf-retry-1")
    assert len(spans) == 13
    result = rules(
        spans, llm=2,
        expect={"StartActivity:get_weather": 1, "RunActivity:get_weather": 2, "get_weather": 2, "RunWorkflow:WeatherAgentWorkflow": 1},
        errors={"RunActivity:get_weather": 1, "get_weather": 1, "RunWorkflow:WeatherAgentWorkflow": 0},
    )
    assert all(result.values()), result
