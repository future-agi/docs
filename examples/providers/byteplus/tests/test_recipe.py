"""The recipe, run as a customer would run it, against the stand-in and a recording
collector. Every assertion is on bytes that really left the process."""
import importlib.util
import json
import sys

import pytest
from conftest import AP_URL, ARK_KEY, EU_URL, FI_API_KEY, FI_SECRET_KEY, MODEL, ROOT, ark_requests, kind, llm_spans

HAS_PROVIDER_TABLE = importlib.util.find_spec("traceai_openai._providers") is not None


def load_app():
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("recipe_app", ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_documented_region_urls_and_the_default():
    app = load_app()
    assert app.REGION_URLS == {"ap": AP_URL, "eu": EU_URL}
    assert app.DEFAULT_REGION == "ap"
    assert app.resolve_base_url({}) == (AP_URL, None)
    assert app.resolve_base_url({"ARK_REGION": "eu"}) == (EU_URL, None)
    assert app.resolve_base_url({"ARK_REGION": "EU"}) == (EU_URL, None)


def test_there_is_no_third_host_and_no_cross_region_fallback():
    app = load_app()
    assert set(app.REGION_URLS.values()) == {AP_URL, EU_URL}
    url, problem = app.resolve_base_url({"ARK_REGION": "cn"})
    assert url is None and "ARK_REGION" in problem


@pytest.mark.parametrize(
    "bad",
    [
        "https://ark.ap-southeast.bytepluses.com/api/coding/v3",
        "https://ark.ap-southeast.bytepluses.com/api/coding",
    ],
)
def test_coding_plan_urls_are_refused_before_anything_is_traced(run_app, collector, stub, bad):
    url, problem = load_app().resolve_base_url({"ARK_BASE_URL": bad})
    assert url is None and "Coding Plan" in problem
    result = run_app(env={"ARK_BASE_URL": bad})
    assert result.returncode == 2
    assert "Coding Plan" in result.stderr
    assert not collector.exports and not ark_requests(stub)


def test_every_scenario_runs_and_the_trace_has_the_expected_shape(run_app, collector):
    result = run_app("--prompt", "hello byteplus")
    assert result.returncode == 0, result.stderr[-1500:]
    for name in ("chat", "stream", "tools", "thinking"):
        assert f"RESULT {name}: echo:" in result.stdout
    assert "RESULT error: HTTP 401" in result.stdout

    spans = collector.spans()
    assert len({s["trace_id"] for s in spans}) == 1
    by_kind = {}
    for s in spans:
        by_kind.setdefault(kind(s), []).append(s)
    assert len(by_kind["AGENT"]) == 1 and len(by_kind["TOOL"]) == 1 and len(by_kind["LLM"]) == 6
    root = by_kind["AGENT"][0]
    assert not root.get("parent_span_id")
    for child in by_kind["LLM"] + by_kind["TOOL"]:
        assert child["parent_span_id"] == root["span_id"]
    assert len({s["_attrs"].get("session.id") for s in spans}) == 1


def test_chat_and_tool_calls_carry_model_and_usage(run_app, collector):
    assert run_app().returncode == 0
    llm = llm_spans(collector)
    chat, tool_first, tool_final = llm[0], llm[2], llm[3]
    for span in (chat, tool_first, tool_final):
        attrs = span["_attrs"]
        assert attrs["gen_ai.request.model"] == MODEL
        assert int(attrs["gen_ai.usage.input_tokens"]) > 0
        assert int(attrs["gen_ai.usage.output_tokens"]) > 0
        assert int(attrs["gen_ai.usage.total_tokens"]) == int(attrs["gen_ai.usage.input_tokens"]) + int(
            attrs["gen_ai.usage.output_tokens"]
        )
        assert span["status"]["code"] == "STATUS_CODE_OK"
    assert "lookup_record" in tool_first["_attrs"]["gen_ai.tool.definitions"]


def test_streaming_with_the_documented_usage_option_has_tokens(run_app, collector, stub):
    assert run_app("--scenario", "stream").returncode == 0
    (stream,) = llm_spans(collector)
    attrs = stream["_attrs"]
    assert int(attrs["gen_ai.usage.total_tokens"]) > 0
    assert [e["name"] for e in stream.get("events", [])] == ["First Token Stream Event"]
    # the option really went to the (stand-in) API
    assert ark_requests(stub)[0]["body"]["stream_options"] == {"include_usage": True}
    # traceai-openai 0.1.10 leaves the model off streamed spans; traceAI PR 249 records it.
    assert attrs.get("gen_ai.request.model") in (None, MODEL)
    assert (attrs.get("gen_ai.request.model") == MODEL) == HAS_PROVIDER_TABLE


def test_streaming_without_the_usage_option_has_no_token_counts(run_app, collector, stub):
    """The docs page tells readers to pass stream_options={"include_usage": True}. Without it
    ModelArk sends no usage chunk, and the span has no token counts."""
    assert run_app("--scenario", "stream", "--no-stream-usage").returncode == 0
    assert "stream_options" not in ark_requests(stub)[0]["body"]
    (stream,) = llm_spans(collector)
    attrs = stream["_attrs"]
    assert not any(k.startswith("gen_ai.usage.") for k in attrs)
    assert stream["status"]["code"] == "STATUS_CODE_OK"


@pytest.mark.parametrize("mode", ["disabled", "enabled"])
def test_thinking_in_extra_body_reaches_the_api_and_still_traces(run_app, collector, stub, mode):
    """G3: the ModelArk `thinking` field rides in extra_body. The call is traced, and the field
    is not a span attribute. With thinking enabled the reasoning text is not on the span either."""
    assert run_app("--scenario", "thinking", "--thinking", mode).returncode == 0
    assert ark_requests(stub)[0]["body"]["thinking"] == {"type": mode}
    (span,) = llm_spans(collector)
    attrs = span["_attrs"]
    assert span["status"]["code"] == "STATUS_CODE_OK"
    assert attrs["gen_ai.request.model"] == MODEL
    assert "thinking" not in attrs.get("gen_ai.request.parameters", "")  # extra_body is not captured
    assert "Reasoning about the request" not in json.dumps(attrs)  # nor is reasoning_content
    if mode == "enabled":
        # reasoning tokens are inside completion_tokens, which is what the span reports
        assert int(attrs["gen_ai.usage.output_tokens"]) > len("echo: Say hello to BytePlus ModelArk in five words.".split())


def test_failed_call_is_an_error_span(run_app, collector):
    assert run_app("--scenario", "error").returncode == 0
    (failed,) = llm_spans(collector)
    assert failed["status"]["code"] == "STATUS_CODE_ERROR"
    assert "AuthenticationError" in failed["status"]["message"] and "401" in failed["status"]["message"]
    assert failed["_attrs"].get("gen_ai.request.model") in (None, MODEL)
    assert "exception" in [e["name"] for e in failed.get("events", [])]


def test_span_model_is_the_model_in_the_response_body(run_app, collector, stub):
    """Observed with the stand-in only: when ModelArk answers with a different model id than the
    one requested (a dated snapshot, say), the non-streaming span shows the response body's model."""
    stub.stub.response_model = "resolved-model-260101"
    assert run_app("--scenario", "chat").returncode == 0
    (span,) = llm_spans(collector)
    assert span["_attrs"]["gen_ai.request.model"] == "resolved-model-260101"


def test_provider_label_is_openai_for_the_byteplus_hosts(run_app, collector):
    assert run_app("--scenario", "chat").returncode == 0
    assert {s["_attrs"]["gen_ai.provider.name"] for s in llm_spans(collector)} == {"openai"}
    if HAS_PROVIDER_TABLE:
        # traceAI PR 249 maps hosts to providers; neither BytePlus host is in its table.
        from traceai_openai._providers import provider_from_host

        for host in ("ark.ap-southeast.bytepluses.com", "ark.eu-west.bytepluses.com"):
            assert provider_from_host(host) == "openai"


def test_each_key_goes_only_where_it_belongs(run_app, collector, stub):
    assert run_app().returncode == 0
    seen = ark_requests(stub)
    assert seen and all(r["path"] == "/api/v3/chat/completions" for r in seen)
    assert {r["authorization"] for r in seen} == {f"Bearer {ARK_KEY}", "Bearer not-a-real-ark-key"}
    blob = json.dumps(seen)
    assert FI_API_KEY not in blob and FI_SECRET_KEY not in blob

    assert collector.exports
    for export in collector.exports:
        assert export["headers"]["x-api-key"] == FI_API_KEY
        assert export["headers"]["x-secret-key"] == FI_SECRET_KEY
        assert "authorization" not in export["headers"]
    assert not any(ARK_KEY in t for t in collector.raw_texts())


def test_export_is_uncompressed_otlp_protobuf_with_project_resource(run_app, collector):
    assert run_app().returncode == 0
    for export in collector.exports:
        assert export["path"] == "/tracer/v1/traces"
        assert export["headers"]["content-type"] == "application/x-protobuf"
        assert "content-encoding" not in export["headers"]
    resource = collector.spans()[0]["_resource"]
    assert resource["project_name"] == "byteplus-test"
    assert resource["project_type"] == "observe"


def test_an_unreachable_collector_never_fails_the_request(run_app):
    result = run_app("--scenario", "chat", fi_base_url="http://127.0.0.1:9")
    assert result.returncode == 0
    assert "RESULT chat: echo:" in result.stdout


def test_missing_configuration_exits_before_tracing(run_app, collector):
    result = run_app(env={"ARK_MODEL": ""})
    assert result.returncode == 2
    assert "ARK_MODEL" in result.stderr
    assert not collector.exports
