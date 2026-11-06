"""The stand-in request body: only published keys, the shapes OpenRouter documents, no invented cost key."""
import json

import broadcast_fixture as bf

# Every attribute key the fixture may write, each traced to an OpenRouter page (retrieved 2026-10-15).
RESOURCE_KEYS = {"service.name", "service.version", "openrouter.trace.id"}          # Grafana, Elastic pages
GENERATION_KEYS = {
    "gen_ai.operation.name", "gen_ai.system", "gen_ai.request.model", "gen_ai.response.model", "gen_ai.response.id",
    "gen_ai.response.finish_reason",                                                   # Grafana, Elastic pages
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.usage.total_tokens",   # same
    "gen_ai.usage.prompt_tokens", "gen_ai.usage.completion_tokens",                   # Webhook page example
    "span.input", "span.output", "gen_ai.prompt", "gen_ai.completion",                # OpenTelemetry Collector page
    "user.id", "session.id",                                                          # same
    "openrouter.inter_token_latency_ms",                                              # Broadcast index
}
PREFIXES = ("trace.metadata.", "span.metadata.openrouter_generation.")                # OpenTelemetry Collector page


def spans(req):
    return req["resourceSpans"][0]["scopeSpans"][0]["spans"]


def keys(span):
    return set(bf.attr_dict(span))


def allowed(key):
    return key in GENERATION_KEYS or key.startswith(PREFIXES)


def test_resource_attributes_are_the_published_three_and_no_project_name():
    res = {a["key"] for a in bf.build_request(bf.Generation())["resourceSpans"][0]["resource"]["attributes"]}
    assert res == RESOURCE_KEYS
    assert "project_name" not in res


def test_extra_resource_attributes_are_only_added_when_asked():
    req = bf.build_request(bf.Generation(), {"project_name": "my-chatbot"})
    res = {a["key"]: a["value"]["stringValue"] for a in req["resourceSpans"][0]["resource"]["attributes"]}
    assert res["project_name"] == "my-chatbot"


def test_every_attribute_key_is_published():
    for g in (bf.Generation(), bf.Generation(cost_metadata=True, privacy_mode=True), bf.Generation(token_style="legacy"),
              bf.Generation(error_message="boom"), bf.Generation(span_name="Step", trace_name="Flow", generation_name="Gen")):
        for span in spans(bf.build_request(g)):
            for k in keys(span) - {"user.id", "session.id"}:
                assert allowed(k) or k.startswith("trace.metadata."), k


def test_no_cost_attribute_is_invented():
    req = bf.build_request(bf.Generation(cost_metadata=True))
    for span in spans(req):
        assert not any(k.endswith("cost") or ".cost" in k for k in keys(span))


def test_generation_span_carries_prompt_and_completion_once_each_way():
    req = bf.build_request(bf.Generation())
    root, gen = spans(req)
    assert {"span.input", "span.output", "gen_ai.prompt", "gen_ai.completion"} <= keys(gen)
    assert not {"trace.input", "trace.output", "span.input", "span.output"} & keys(root)


def test_privacy_mode_drops_content_and_never_writes_empty_strings():
    req = bf.build_request(bf.Generation(privacy_mode=True, cost_metadata=True))
    root, gen = spans(req)
    assert not {"span.input", "span.output", "gen_ai.prompt", "gen_ai.completion"} & keys(gen)
    for span in spans(req):
        assert "" not in bf.attr_dict(span).values()
    a = bf.attr_dict(gen)
    assert a["span.metadata.openrouter_generation.upstream_raw_response_usage"] == "null"
    assert a["span.metadata.openrouter_generation.upstream_raw_response_usage_suppression_reason"] == "privacy_mode"
    assert a["gen_ai.usage.input_tokens"] == 9          # usage, model and metadata still arrive


def test_cost_metadata_is_on_both_root_and_generation_span_as_documented():
    root, gen = spans(bf.build_request(bf.Generation(cost_metadata=True)))
    assert "trace.metadata.openrouter_generation.usage_is_estimated" in keys(root)
    assert "span.metadata.openrouter_generation.usage_is_estimated" in keys(gen)
    assert bf.attr_dict(gen)["span.metadata.openrouter_generation.usage_is_estimated"] is False   # false is kept, not dropped


def test_default_has_no_openrouter_generation_metadata():
    root, gen = spans(bf.build_request(bf.Generation()))
    assert not any("openrouter_generation" in k for k in keys(root) | keys(gen))


def test_integers_are_strings_in_otlp_json_like_openrouters_example():
    gen = spans(bf.build_request(bf.Generation(input_tokens=100, output_tokens=50)))[-1]
    tokens = [a for a in gen["attributes"] if a["key"] == "gen_ai.usage.input_tokens"][0]
    assert tokens["value"] == {"intValue": "100"}
    assert isinstance(gen["startTimeUnixNano"], str)


def test_token_key_spelling_follows_style():
    cur = bf.attr_dict(spans(bf.build_request(bf.Generation(token_style="current")))[-1])
    old = bf.attr_dict(spans(bf.build_request(bf.Generation(token_style="legacy")))[-1])
    assert {"gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.usage.total_tokens"} <= set(cur)
    assert "gen_ai.usage.prompt_tokens" in old and "gen_ai.usage.input_tokens" not in old


def test_unavailable_usage_is_omitted_not_zero():
    gen = spans(bf.build_request(bf.Generation(input_tokens=None, output_tokens=None)))[-1]
    assert not [k for k in keys(gen) if k.startswith("gen_ai.usage.")]


def test_user_and_session_map_to_user_id_and_session_id():
    root, gen = spans(bf.build_request(bf.Generation(user="u1", session_id="s1")))
    assert bf.attr_dict(gen)["user.id"] == "u1" and bf.attr_dict(gen)["session.id"] == "s1"
    none = spans(bf.build_request(bf.Generation(user=None, session_id=None)))[-1]
    assert "user.id" not in keys(none) and "session.id" not in keys(none)


def test_custom_trace_metadata_goes_under_trace_metadata():
    gen = spans(bf.build_request(bf.Generation(metadata={"environment": "staging", "deployment": "us-east-1"})))[-1]
    a = bf.attr_dict(gen)
    assert a["trace.metadata.environment"] == "staging" and a["trace.metadata.deployment"] == "us-east-1"


def test_span_tree_default_and_named():
    root, gen = spans(bf.build_request(bf.Generation(model="openai/gpt-4o")))
    assert root["name"] == gen["name"] == "openai/gpt-4o"           # names default to the model slug
    assert gen["parentSpanId"] == root["spanId"] and "parentSpanId" not in root
    r, mid, g = spans(bf.build_request(bf.Generation(trace_name="Doc", span_name="Step", generation_name="Gen")))
    assert (r["name"], mid["name"], g["name"]) == ("Doc", "Step", "Gen")
    assert mid["parentSpanId"] == r["spanId"] and g["parentSpanId"] == mid["spanId"]


def test_trace_id_and_parent_span_id_join_the_callers_trace():
    req = bf.build_request(bf.Generation(trace_id="0123456789abcdef0123456789abcdef", parent_span_id="0123456789abcdef"))
    root = spans(req)[0]
    assert {s["traceId"] for s in spans(req)} == {"0123456789abcdef0123456789abcdef"}
    assert root["parentSpanId"] == "0123456789abcdef"


def test_generated_ids_are_valid_hex_of_the_right_length():
    s = spans(bf.build_request(bf.Generation()))
    assert len(s[0]["traceId"]) == 32 and int(s[0]["traceId"], 16) >= 0
    assert all(len(x["spanId"]) == 16 for x in s) and len({x["spanId"] for x in s}) == len(s)


def test_error_is_an_otlp_error_status_on_the_generation_span_only():
    root, gen = spans(bf.build_request(bf.Generation(error_message="rate limited")))
    assert gen["status"] == {"code": bf.STATUS_ERROR, "message": "rate limited"}
    assert root["status"]["code"] == bf.STATUS_UNSET
    assert "gen_ai.response.model" not in keys(gen)             # a failed request has no response


def test_exception_event_is_synthetic_and_only_on_failures():
    ok = spans(bf.build_request(bf.Generation(exception_event=True)))[-1]
    assert "events" not in ok
    bad = spans(bf.build_request(bf.Generation(error_message="x", exception_event=True)))[-1]
    assert bad["events"][0]["name"] == "exception"


def test_big_chars_pads_the_prompt_copies():
    gen = spans(bf.build_request(bf.Generation(big_chars=5000)))[-1]
    a = bf.attr_dict(gen)
    assert len(a["span.input"]) > 5000 and a["span.input"] == a["gen_ai.prompt"]


def test_test_connection_request_is_an_empty_resource_spans_list():
    assert bf.test_connection_request() == {"resourceSpans": []}


def test_request_is_json_serialisable():
    json.dumps(bf.build_request(bf.Generation(cost_metadata=True, span_name="s")))
