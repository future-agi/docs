"""gateway_fixture.py: the stand-in's request body follows Cloudflare's documented attribute names."""
import pytest

import gateway_fixture as gf


def span_of(req):
    return req["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


def test_documented_attributes_use_cloudflares_names():
    r = gf.GatewayRequest(model="gpt-4o", provider="openai", input_tokens=11, output_tokens=7)
    a = gf.attr_dict(span_of(gf.build_request(r)))
    assert a["gen_ai.request.model"] == "gpt-4o"
    assert a["gen_ai.model.provider"] == "openai"
    assert "gen_ai.provider.name" not in a               # Cloudflare's name is gen_ai.model.provider
    assert a["gen_ai.usage.input_tokens"] == 11 and a["gen_ai.usage.output_tokens"] == 7
    assert isinstance(a["gen_ai.usage.cost"], float)
    assert a["gen_ai.prompt_json"].startswith("[") and a["gen_ai.completion_json"].startswith("{")


def test_cost_is_the_given_value_when_given():
    a = gf.attr_dict(span_of(gf.build_request(gf.GatewayRequest(cost=0.125))))
    assert a["gen_ai.usage.cost"] == 0.125


def test_metadata_keys_become_attributes_and_gen_ai_keys_are_dropped():
    r = gf.GatewayRequest(metadata={"user_id": "user123", "team": "engineering", "gen_ai.request.model": "spoof"})
    a = gf.attr_dict(span_of(gf.build_request(r)))
    assert a["user_id"] == "user123" and a["team"] == "engineering"
    assert a["gen_ai.request.model"] == "gpt-4o-mini"      # the real one, not the spoof


def test_trace_context_headers_set_trace_and_parent_ids():
    tid, sid = "a1b2c3d4e5f60718293a4b5c6d7e8f90", "a1b2c3d4e5f60718"
    s = span_of(gf.build_request(gf.GatewayRequest(otel_trace_id=tid, otel_parent_span_id=sid)))
    assert s["traceId"] == tid and s["parentSpanId"] == sid


def test_without_the_headers_a_new_trace_id_is_made():
    s1 = span_of(gf.build_request(gf.GatewayRequest()))
    s2 = span_of(gf.build_request(gf.GatewayRequest()))
    assert len(s1["traceId"]) == 32 and s1["traceId"] != s2["traceId"] and "parentSpanId" not in s1


@pytest.mark.parametrize("tid,sid", [("a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6", None), (None, "a1b2c3d4e5f6g7h8"), ("abc", None), (None, "ABCDEF0123456789")])
def test_ids_that_are_not_lowercase_hex_are_refused(tid, sid):
    # The example values on Cloudflare's page contain letters outside 0-9a-f; real ids must be hex.
    with pytest.raises(ValueError):
        gf.build_span(gf.GatewayRequest(otel_trace_id=tid, otel_parent_span_id=sid))


def test_error_request_is_status_error_with_an_optional_exception_event():
    s = span_of(gf.build_request(gf.GatewayRequest(error_message="Provider returned 429", completion=None, exception_event=True)))
    assert s["status"] == {"code": 2, "message": "Provider returned 429"}
    assert s["events"][0]["name"] == "exception"
    assert "events" not in span_of(gf.build_request(gf.GatewayRequest(error_message="x", completion=None)))


def test_missing_usage_and_prompt_are_absent_not_zero():
    a = gf.attr_dict(span_of(gf.build_request(gf.GatewayRequest(input_tokens=None, output_tokens=None, prompt=None))))
    assert "gen_ai.usage.input_tokens" not in a and "gen_ai.usage.output_tokens" not in a
    assert "gen_ai.prompt_json" not in a and "gen_ai.usage.cost" not in a


def test_resource_has_no_project_name_unless_a_stamp_is_simulated():
    keys = [x["key"] for x in gf.build_request(gf.GatewayRequest())["resourceSpans"][0]["resource"]["attributes"]]
    assert "project_name" not in keys
    keys = [x["key"] for x in gf.build_request(gf.GatewayRequest(), {"project_name": "p"})["resourceSpans"][0]["resource"]["attributes"]]
    assert "project_name" in keys


def test_protobuf_round_trip_keeps_ids_and_attributes():
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    req = gf.build_request(gf.GatewayRequest(otel_trace_id="0123456789abcdef0123456789abcdef", otel_parent_span_id="0123456789abcdef"), {"project_name": "p"})
    msg = ExportTraceServiceRequest()
    msg.ParseFromString(gf.to_protobuf(req))
    sp = msg.resource_spans[0].scope_spans[0].spans[0]
    assert sp.trace_id.hex() == "0123456789abcdef0123456789abcdef" and sp.parent_span_id.hex() == "0123456789abcdef"
    assert {a.key for a in sp.attributes} >= {"gen_ai.request.model", "gen_ai.model.provider", "gen_ai.prompt_json"}


def test_caller_span_is_the_parent_of_the_linked_gateway_span():
    c = gf.build_caller_request("0" * 31 + "1", "1" * 16, {"project_name": "p"})
    assert span_of(c)["spanId"] == "1" * 16 and "parentSpanId" not in span_of(c)
