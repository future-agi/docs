"""The recipe, run as a customer would run it, against the stand-in gateway and a
recording collector. Every assertion is on bytes that really left the process."""
import importlib.util
import json
import sys
import urllib.request

import pytest
from conftest import FI_API_KEY, FI_SECRET_KEY, GATEWAY_KEY, MODEL, ROOT, gateway_requests

HAS_PROVIDER_TABLE = importlib.util.find_spec("traceai_openai._providers") is not None


def kind(span):
    return span["_attrs"].get("gen_ai.span.kind")


def llm_spans(collector):
    return sorted((s for s in collector.spans() if kind(s) == "LLM"), key=lambda s: int(s["start_time_unix_nano"]))


def test_documented_gateway_url_is_the_default():
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("recipe_app", ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEFAULT_BASE_URL == "https://ai-gateway.vercel.sh/v1"


def test_every_scenario_runs_and_the_trace_has_the_expected_shape(run_app, collector):
    result = run_app("--prompt", "hello gateway")
    assert result.returncode == 0, result.stderr[-1500:]
    for name in ("chat", "stream", "tools"):
        assert f"RESULT {name}: echo:" in result.stdout
    assert "RESULT error: HTTP 401" in result.stdout

    spans = collector.spans()
    assert len({s["trace_id"] for s in spans}) == 1
    by_kind = {}
    for s in spans:
        by_kind.setdefault(kind(s), []).append(s)
    assert len(by_kind["AGENT"]) == 1 and len(by_kind["TOOL"]) == 1 and len(by_kind["LLM"]) == 5
    root = by_kind["AGENT"][0]
    assert not root.get("parent_span_id")
    for child in by_kind["LLM"] + by_kind["TOOL"]:
        assert child["parent_span_id"] == root["span_id"]
    # one session for the whole run
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


def test_streaming_without_reported_usage_has_no_token_attributes(run_app, collector):
    assert run_app("--scenario", "stream").returncode == 0
    (stream,) = llm_spans(collector)
    attrs = stream["_attrs"]
    # Unknown is not zero: no usage in the stream means no token attributes, not 0.
    assert not [k for k in attrs if k.startswith("gen_ai.usage.")]
    assert [e["name"] for e in stream.get("events", [])] == ["First Token Stream Event"]
    # traceai-openai 0.1.10 leaves the model off streamed spans; traceAI PR 249 records it.
    assert attrs.get("gen_ai.request.model") in (None, MODEL)
    assert (attrs.get("gen_ai.request.model") == MODEL) == HAS_PROVIDER_TABLE


def test_failed_call_is_an_error_span(run_app, collector):
    assert run_app("--scenario", "error").returncode == 0
    (failed,) = llm_spans(collector)
    assert failed["status"]["code"] == "STATUS_CODE_ERROR"
    assert "401" in failed["status"]["message"]
    assert failed["_attrs"].get("gen_ai.request.model") in (None, MODEL)
    assert "exception" in [e["name"] for e in failed.get("events", [])]


@pytest.mark.parametrize("scenario", ["chat", "tools"])
def test_span_model_is_the_model_in_the_response_body(run_app, collector, stub, scenario):
    """Observed with the stand-in only: when the gateway answers with a different model id
    (Vercel's drain documents gen_ai.response.model as the resolved canonical model), the
    span shows the response body's model. Not checked against a live gateway."""
    stub.stub.response_model = "resolved-model-2026-10-01"
    assert run_app("--scenario", scenario).returncode == 0
    first = llm_spans(collector)[0]
    assert first["_attrs"]["gen_ai.request.model"] == "resolved-model-2026-10-01"


def test_provider_label_is_openai_for_the_gateway_host():
    """traceai-openai labels every OpenAI-client span provider=openai. The host table in
    traceAI PR 249 does not know ai-gateway.vercel.sh, so it keeps that label."""
    if not HAS_PROVIDER_TABLE:
        pytest.skip("host table ships with traceAI PR 249; 0.1.10 always says openai")
    from traceai_openai._providers import provider_from_host

    assert provider_from_host("ai-gateway.vercel.sh") == "openai"


def test_each_key_goes_only_where_it_belongs(run_app, collector, stub):
    assert run_app().returncode == 0
    seen = gateway_requests(stub)
    assert seen and all(r["path"] == "/v1/chat/completions" for r in seen)
    assert {r["authorization"] for r in seen} == {f"Bearer {GATEWAY_KEY}", "Bearer not-a-real-gateway-key"}
    blob = json.dumps(seen)
    assert FI_API_KEY not in blob and FI_SECRET_KEY not in blob

    assert collector.exports
    for export in collector.exports:
        assert export["headers"]["x-api-key"] == FI_API_KEY
        assert export["headers"]["x-secret-key"] == FI_SECRET_KEY
        assert "authorization" not in export["headers"]
    assert not any(GATEWAY_KEY in t for t in collector.raw_texts())


def test_export_is_uncompressed_otlp_protobuf_with_project_resource(run_app, collector):
    assert run_app().returncode == 0
    for export in collector.exports:
        assert export["path"] == "/tracer/v1/traces"
        assert export["headers"]["content-type"] == "application/x-protobuf"
        assert "content-encoding" not in export["headers"]
    resource = collector.spans()[0]["_resource"]
    assert resource["project_name"] == "vercel-ai-gateway-test"
    assert resource["project_type"] == "observe"


def test_an_unreachable_collector_never_fails_the_request(run_app):
    result = run_app("--scenario", "chat", fi_base_url="http://127.0.0.1:9")
    assert result.returncode == 0
    assert "RESULT chat: echo:" in result.stdout


def test_missing_configuration_exits_before_tracing(run_app):
    result = run_app(env={"AI_GATEWAY_MODEL": ""})
    assert result.returncode == 2
    assert "AI_GATEWAY_MODEL" in result.stderr


def test_stub_log_is_reachable_for_debugging(stub):
    with urllib.request.urlopen(stub.url.replace("/v1", "") + "/healthz") as resp:
        assert json.load(resp) == {"ok": True}
