"""The synthetic AI Gateway trace builder: the shape the collector recipe is tested with."""
import gateway_trace as g  # noqa: E402  (conftest puts the example dir on sys.path)


def attrs(span):
    return {a.key: a.value for a in span.attributes}


def test_ok_scenario_has_root_policy_children_and_a_model_call():
    req, tid = g.build("ok", project_name="p", marker="M")
    spans = req.resource_spans[0].scope_spans[0].spans
    assert len(spans) == 4 and len(tid) == 32
    root = spans[0]
    assert not root.parent_span_id and all(s.parent_span_id == root.span_id for s in spans[1:])
    assert [a.value.string_value for a in req.resource_spans[0].resource.attributes if a.key == "project_name"] == ["p"]
    assert any(k.startswith("azure.ai_gateway.identity.claims.") for k in attrs(root))
    model = [s for s in spans if attrs(s).get("gen_ai.usage.input_tokens")]
    assert model and attrs(model[0])["gen_ai.usage.output_tokens"].int_value == 42


def test_no_project_name_means_no_resource_attribute():
    req, _ = g.build("ok")
    assert "project_name" not in {a.key for a in req.resource_spans[0].resource.attributes}


def test_blocked_scenario_is_an_error_with_exception_text_for_the_scrub_to_remove():
    req, _ = g.build("blocked", marker="MK")
    spans = req.resource_spans[0].scope_spans[0].spans
    assert len(spans) == 3
    assert spans[0].status.code == 2 and "MK" in spans[0].status.message
    assert {a.key for a in spans[0].events[0].attributes} >= {"exception.message", "exception.stacktrace"}


def test_content_only_with_the_flag():
    plain = g.build("ok", marker="MK")[0].SerializeToString()
    withc = g.build("ok", marker="MK", with_content=True)[0].SerializeToString()
    assert b"MK" not in plain and b"MK" in withc
