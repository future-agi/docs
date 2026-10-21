"""replay_spans.py turns spans from TrueFoundry's Query Spans API into an OTLP batch.

The fixture mirrors the shape of real gateway spans read on 2026-10-20 (values are placeholders):
root `ChatCompletion: <model>` (Server), `Model: <model>` (Internal), and the provider call
`POST https://api.openai.com/...` (Client), each one the child of the span before.
"""
import replay_spans

TRACE = "01a158290d2b72b09314c98e36cacd9d"
ROWS = [
    {"traceId": TRACE, "spanId": "aaaaaaaaaaaaaaaa", "parentSpanId": "", "spanName": "ChatCompletion: acct/m",
     "spanKind": "Server", "scopeName": "@opentelemetry/instrumentation-http", "scopeVersion": "0.1",
     "timestamp": "2026-10-20T07:14:07.791Z", "durationNs": 1_000_000_000, "statusCode": "Ok", "statusMessage": "",
     "spanAttributes": {"tfy.input": "SECRET", "tfy.span_type": "ChatCompletion", "tfy.model.streaming": False,
                        "tfy.model.metric.input_tokens": 118, "tfy.request.metadata": {"tfy_gateway_region": "US"},
                        "tfy.request.created_by_subject_teams": ["everyone"]}},
    {"traceId": TRACE, "spanId": "bbbbbbbbbbbbbbbb", "parentSpanId": "aaaaaaaaaaaaaaaa", "spanName": "Model: acct/m",
     "spanKind": "Internal", "scopeName": "tfy-llm-gateway", "timestamp": "2026-10-20T07:14:07.800Z",
     "durationNs": 900_000_000, "statusCode": "Error", "statusMessage": "boom", "spanAttributes": {}},
    {"traceId": "ff" * 16, "spanId": "cccccccccccccccc", "parentSpanId": "", "spanName": "other", "spanKind": "Server",
     "scopeName": "x", "timestamp": "2026-10-20T07:14:08.000Z", "durationNs": 1, "statusCode": "Unset", "spanAttributes": {}},
]


def _spans(req):
    return [sp for ss in req.resource_spans[0].scope_spans for sp in ss.spans]


def test_trace_filter_ids_parent_links_status_and_kinds():
    req = replay_spans.build_request(ROWS, trace_ids=[TRACE], resource={"project_name": "p"})
    root, model = sorted(_spans(req), key=lambda s: s.start_time_unix_nano)
    assert root.trace_id.hex() == TRACE and root.span_id.hex() == "aaaaaaaaaaaaaaaa" and root.parent_span_id == b""
    assert model.parent_span_id == root.span_id
    assert root.status.code == root.status.STATUS_CODE_OK
    assert model.status.code == model.status.STATUS_CODE_ERROR and model.status.message == "boom"
    assert root.end_time_unix_nano - root.start_time_unix_nano == 1_000_000_000
    res = {kv.key: kv.value.string_value for kv in req.resource_spans[0].resource.attributes}
    assert res == {"service.name": "tfy-llm-gateway", "project_name": "p"}


def test_attribute_types_survive_including_the_metadata_object():
    req = replay_spans.build_request(ROWS, trace_ids=[TRACE])
    root = [s for s in _spans(req) if s.name.startswith("ChatCompletion")][0]
    a = {kv.key: kv.value for kv in root.attributes}
    assert a["tfy.model.metric.input_tokens"].int_value == 118
    assert a["tfy.model.streaming"].bool_value is False
    assert a["tfy.request.created_by_subject_teams"].array_value.values[0].string_value == "everyone"
    assert a["tfy.request.metadata"].kvlist_value.values[0].key == "tfy_gateway_region"


def test_drop_content_removes_only_the_three_documented_keys():
    req = replay_spans.build_request(ROWS, trace_ids=[TRACE], drop_content=True)
    root = [s for s in _spans(req) if s.name.startswith("ChatCompletion")][0]
    keys = {kv.key for kv in root.attributes}
    assert "tfy.input" not in keys and "tfy.span_type" in keys
