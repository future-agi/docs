"""The synthetic TrueFoundry-shaped batches and the poster that sends them."""
import base64
import json

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.trace.v1.trace_pb2 import Status

from post_batch import auth_headers, to_otlp_json
from tfy_batch import ACCOUNT_MODEL, CONTENT_KEYS, build_batch

MARK = "TFYMARK7"


def attrs_of(pb_attrs):
    out = {}
    for kv in pb_attrs:
        which = kv.value.WhichOneof("value")
        value = getattr(kv.value, which)
        out[kv.key] = [v.string_value for v in value.values] if which == "array_value" else value
    return out


def spans(req):
    rs = req.resource_spans[0]
    root, model = rs.scope_spans[0].spans
    return attrs_of(rs.resource.attributes), root, model


def test_default_batch_matches_what_the_gateway_sends_without_extra_resource_attributes():
    resource, root, model = spans(build_batch(MARK))
    assert resource == {"service.name": "tfy-llm-gateway"}
    assert "project_name" not in resource  # the collector rejects this batch
    assert root.name == "ChatCompletion" and model.name == f"Model: {ACCOUNT_MODEL}"
    assert model.parent_span_id == root.span_id and root.parent_span_id == b""
    assert model.trace_id == root.trace_id


def test_additional_resource_attributes_land_on_the_resource():
    resource, _, _ = spans(build_batch(MARK, resource_attrs={"project_name": "p", "project_type": "observe"}))
    assert resource["project_name"] == "p" and resource["project_type"] == "observe"


def test_genai_flag_off_has_only_tfy_attributes():
    _, root, model = spans(build_batch(MARK, genai=False))
    for span in (root, model):
        assert not [k for k in attrs_of(span.attributes) if k.startswith("gen_ai.")]
    assert attrs_of(model.attributes)["tfy.model.metric.input_tokens"] == 34


def test_genai_flag_on_uses_the_documented_current_names_not_the_blog_names():
    _, _, model = spans(build_batch(MARK, genai=True))
    a = attrs_of(model.attributes)
    assert a["gen_ai.usage.input_tokens"] == 34 and a["gen_ai.usage.output_tokens"] == 19
    assert a["gen_ai.provider.name"] == "openai" and a["gen_ai.request.model"] == ACCOUNT_MODEL
    assert "gen_ai.system" not in a and "gen_ai.usage.prompt_tokens" not in a  # names from the older blog post


def test_content_off_has_no_prompt_or_response_text():
    raw = build_batch(MARK, content="off").SerializeToString()
    assert b"Summarise ticket" not in raw and b"cannot log in" not in raw
    _, root, model = spans(build_batch(MARK, content="off"))
    for span in (root, model):
        keys = attrs_of(span.attributes)
        assert not [k for k in (*CONTENT_KEYS, "gen_ai.input.messages", "gen_ai.output.messages") if k in keys]


def test_exclude_literal_removes_only_the_three_documented_keys():
    _, root, model = spans(build_batch(MARK, content="exclude_literal"))
    for span in (root, model):
        a = attrs_of(span.attributes)
        assert not [k for k in CONTENT_KEYS if k in a]
        assert MARK in a["gen_ai.input.messages"]  # still there: the case the collector recipe covers
    assert MARK in attrs_of(root.attributes)["tfy.request.metadata"]


def test_failure_sets_error_status_and_tfy_error_type():
    _, root, model = spans(build_batch(MARK, failure=True))
    for span in (root, model):
        assert span.status.code == Status.STATUS_CODE_ERROR
        a = attrs_of(span.attributes)
        assert a["tfy.error_type"] == "tfy-forbidden" and a["error.type"] == "tfy-forbidden"
        assert MARK in a["tfy.error_message"]


def test_ids_never_contain_the_marker():
    req = build_batch(MARK)
    text = json.dumps(attrs_of(req.resource_spans[0].scope_spans[0].spans[0].attributes))
    assert "conv-" in text
    assert MARK.lower() not in text.split("conv-")[1].split('"')[0]


def test_wire_roundtrip():
    req = build_batch(MARK)
    again = ExportTraceServiceRequest()
    again.ParseFromString(req.SerializeToString())
    assert again == req


def test_otlp_json_uses_hex_ids():
    req = build_batch(MARK)
    doc = json.loads(to_otlp_json(req))
    span = doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["traceId"] == req.resource_spans[0].scope_spans[0].spans[0].trace_id.hex()
    assert len(span["spanId"]) == 16 and "parentSpanId" not in span


def test_auth_modes(monkeypatch):
    monkeypatch.setenv("FI_API_KEY", "ak")
    monkeypatch.setenv("FI_SECRET_KEY", "sk")
    assert auth_headers("headers") == {"X-Api-Key": "ak", "X-Secret-Key": "sk"}
    assert auth_headers("basic")["Authorization"] == "Basic " + base64.b64encode(b"ak:sk").decode()
    assert auth_headers("bearer") == {"Authorization": "Bearer ak"}
    assert auth_headers("none") == {}
    wrong = auth_headers("wrong")
    assert set(wrong) == {"X-Api-Key", "X-Secret-Key"} and "ak" not in wrong.values() and "sk" not in wrong.values()


def test_failure_without_error_status_leaves_the_otlp_status_unset():
    _, root, model = spans(build_batch(MARK, failure=True, error_status=False))
    for span in (root, model):
        assert span.status.code == Status.STATUS_CODE_UNSET
        assert attrs_of(span.attributes)["tfy.error_type"] == "tfy-forbidden"


def test_exception_event_is_opt_in_and_only_on_the_model_span_of_a_failure():
    _, root, model = spans(build_batch(MARK, failure=True, exception_event=True))
    assert not root.events
    (event,) = model.events
    assert event.name == "exception"
    assert {"exception.message", "exception.stacktrace"} <= set(attrs_of(event.attributes))
    _, _, ok_model = spans(build_batch(MARK, failure=False, exception_event=True))
    assert not ok_model.events


def test_identity_and_variable_attributes_are_present_for_the_privacy_tests():
    _, root, _ = spans(build_batch(MARK))
    a = attrs_of(root.attributes)
    assert MARK in a["tfy.prompt_variables"]
    assert a["tfy.request.created_by_subject_teams"] == [f"team-{MARK.lower()}"]
