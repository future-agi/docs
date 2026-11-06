"""The recipe, run exactly as a customer runs it: a separate process, the real `openai`
SDK and the real traceAI-openai instrumentor, a Z.ai-shaped stand-in, and a recording
collector in place of Future AGI."""
import json
import uuid

import pytest
from conftest import (
    CODING_PLAN_URLS,
    FI_API_KEY,
    FI_SECRET_KEY,
    MODEL,
    ZAI_KEY,
    ZAI_URL,
    kind,
    llm_spans,
    zai_requests,
)

import app


def by_start(collector, wanted_kind):
    return sorted((s for s in collector.spans() if kind(s) == wanted_kind), key=lambda s: int(s["start_time_unix_nano"]))


def test_the_supported_base_url_is_the_one_in_zais_openai_guide():
    assert app.ZAI_BASE_URL == "https://api.z.ai/api/paas/v4/" == ZAI_URL
    assert app.resolve_base_url({}) == (ZAI_URL, None)


@pytest.mark.parametrize(
    "url",
    list(CODING_PLAN_URLS)
    + [u + "/" for u in CODING_PLAN_URLS]
    + ["HTTPS://API.Z.AI/API/CODING/PAAS/V4", "https://api.z.ai/api/anthropic/v1/messages", "https://api.z.ai/api/v1/"],
)
def test_the_three_coding_plan_urls_are_refused(url):
    base, problem = app.resolve_base_url({"ZAI_BASE_URL": url})
    assert base is None
    assert "Coding Plan" in problem


@pytest.mark.parametrize("url", ["https://api.z.ai/api/paas/v4/", "https://api.z.ai/api/paas/v4", "http://127.0.0.1:9/api/paas/v4/"])
def test_the_general_platform_url_is_not_refused(url):
    assert app.resolve_base_url({"ZAI_BASE_URL": url}) == (url, None)


def test_the_app_exits_before_any_call_when_given_a_coding_plan_url(run_app, collector, stub):
    result = run_app("--scenario", "chat", env={"ZAI_BASE_URL": CODING_PLAN_URLS[1]}, use_stub=False)
    assert result.returncode == 2
    assert "Coding Plan" in result.stderr
    assert collector.exports == []
    assert zai_requests(stub) == []


def test_chat_makes_one_llm_span_under_the_project_with_model_and_tokens(run_app, collector, stub):
    result = run_app("--scenario", "chat", "--prompt", "hello there")
    assert result.returncode == 0, result.stderr[-1500:]
    assert "RESULT chat: Z.ai stand-in reply to: hello there" in result.stdout
    spans = collector.spans()
    assert {kind(s) for s in spans} == {"AGENT", "LLM"}
    (llm,) = llm_spans(collector)
    (agent,) = by_start(collector, "AGENT")
    assert llm["parent_span_id"] == agent["span_id"]
    assert llm["trace_id"] == agent["trace_id"]
    a = llm["_attrs"]
    assert a["gen_ai.request.model"] == MODEL
    assert a["gen_ai.provider.name"] == "openai"
    # the stand-in counts words: 2 in the prompt, 6 in "Z.ai stand-in reply to: hello there"
    assert int(a["gen_ai.usage.input_tokens"]) == 2
    assert int(a["gen_ai.usage.output_tokens"]) == 6
    assert int(a["gen_ai.usage.total_tokens"]) == 8
    assert llm["_resource"]["project_name"] == "z-ai-test"
    assert llm["status"]["code"] == "STATUS_CODE_OK"
    # what reached "Z.ai": the documented path, a bearer key, the model
    (req,) = zai_requests(stub)
    assert req["path"] == "/api/paas/v4/chat/completions"
    assert req["authorization_matches"] is True
    assert req["body"]["model"] == MODEL


def test_the_whole_run_is_one_trace_and_one_session(run_app, collector):
    session = f"s-{uuid.uuid4()}"
    result = run_app("--session-id", session)
    assert result.returncode == 0, result.stderr[-1500:]
    spans = collector.spans()
    assert len({s["trace_id"] for s in spans}) == 1
    assert {s["_attrs"].get("session.id") for s in spans} == {session}
    assert f"session_id={session}" in result.stdout


def test_stream_reports_tokens_from_the_last_chunk_without_stream_options(run_app, collector, stub):
    result = run_app("--scenario", "stream", "--prompt", "one two three")
    assert result.returncode == 0, result.stderr[-1500:]
    assert "RESULT stream: Z.ai stand-in reply to: one two three" in result.stdout
    (req,) = zai_requests(stub)
    assert req["body"]["stream"] is True
    assert "stream_options" not in req["body"], "Z.ai documents usage on the last chunk; the recipe must not need stream_options"
    (llm,) = llm_spans(collector)
    a = llm["_attrs"]
    assert int(a["gen_ai.usage.input_tokens"]) == 3
    assert int(a["gen_ai.usage.output_tokens"]) == 7
    assert int(a["gen_ai.usage.total_tokens"]) == 10
    assert [e["name"] for e in llm.get("events", [])] == ["First Token Stream Event"]
    assert a["output.value"] == "Z.ai stand-in reply to: one two three"


def test_tool_round_trip_is_two_llm_spans_and_your_own_tool_span(run_app, collector):
    result = run_app("--scenario", "tools", "--prompt", "find the record")
    assert result.returncode == 0, result.stderr[-1500:]
    assert "RESULT tools: The lookup returned: record for find the record" in result.stdout
    first, second = llm_spans(collector)
    (tool,) = by_start(collector, "TOOL")
    (agent,) = by_start(collector, "AGENT")
    assert {first["parent_span_id"], second["parent_span_id"], tool["parent_span_id"]} == {agent["span_id"]}
    a1, a2 = first["_attrs"], second["_attrs"]
    assert a1["gen_ai.output.messages.0.message.tool_calls.0.tool_call.function.name"] == "lookup_record"
    assert json.loads(a1["gen_ai.output.messages.0.message.tool_calls.0.tool_call.function.arguments"]) == {"query": "find the record"}
    assert json.loads(a1["gen_ai.tool.definitions"])[0]["function"]["name"] == "lookup_record"
    assert a2["gen_ai.input.messages.2.message.role"] == "tool"
    assert a2["gen_ai.output.messages.0.message.content"] == "The lookup returned: record for find the record"
    for a in (a1, a2):
        assert a["gen_ai.request.model"] == MODEL
        assert int(a["gen_ai.usage.total_tokens"]) > 0


def test_thinking_passes_through_to_zai_but_reasoning_text_is_not_on_the_span(run_app, collector, stub):
    result = run_app("--scenario", "thinking", "--prompt", "why is the sky blue")
    assert result.returncode == 0, result.stderr[-1500:]
    (req,) = zai_requests(stub)
    assert req["body"]["thinking"] == {"type": "enabled"}
    (llm,) = llm_spans(collector)
    exported = json.dumps(llm)
    assert "Stand-in reasoning" not in exported, "reasoning_content is not recorded by traceAI-openai 0.1.10"
    assert "reasoning_content" not in exported
    assert "thinking" not in llm["_attrs"]["gen_ai.request.parameters"]
    # the reasoning tokens are inside the usage the response reports, and that is what the span carries
    assert int(llm["_attrs"]["gen_ai.usage.output_tokens"]) > len("Z.ai stand-in reply to: why is the sky blue".split())


def test_a_failed_call_is_an_error_span_with_the_http_status(run_app, collector):
    result = run_app("--scenario", "error")
    assert result.returncode == 0, result.stderr[-1500:]
    assert "RESULT error: HTTP 401" in result.stdout
    (llm,) = llm_spans(collector)
    assert llm["status"]["code"] == "STATUS_CODE_ERROR"
    assert "401" in llm["status"]["message"]
    assert "AuthenticationError" in llm["status"]["message"]
    assert [e["name"] for e in llm.get("events", [])] == ["exception"]
    assert llm["_attrs"]["gen_ai.provider.name"] == "openai"
    assert llm["_resource"]["project_name"] == "z-ai-test"


def test_provider_label_reads_openai_for_every_call(run_app, collector):
    assert run_app().returncode == 0
    labels = {s["_attrs"]["gen_ai.provider.name"] for s in llm_spans(collector)}
    assert labels == {"openai"}


def test_keys_go_only_where_they_belong(run_app, collector, stub):
    assert run_app().returncode == 0
    reqs = zai_requests(stub)
    assert reqs and all(r["authorization_scheme"] == "Bearer" for r in reqs)
    for r in reqs:
        assert "x-api-key" not in r["header_names"] and "x-secret-key" not in r["header_names"]
        assert FI_API_KEY not in json.dumps(r["body"]) and FI_SECRET_KEY not in json.dumps(r["body"])
    exported = "\n".join(collector.raw_texts())
    assert ZAI_KEY not in exported
    assert "not-a-real-zai-key" not in exported
    assert "Bearer" not in exported
    for export in collector.exports:
        assert export["headers"]["x-api-key"] == FI_API_KEY
        assert export["headers"]["x-secret-key"] == FI_SECRET_KEY


def test_export_is_uncompressed_otlp_http_with_project_name(run_app, collector):
    assert run_app("--scenario", "chat").returncode == 0
    assert collector.exports
    for export in collector.exports:
        assert export["path"] == "/tracer/v1/traces"
        assert "content-encoding" not in export["headers"]
        assert export["headers"]["content-type"] == "application/x-protobuf"
    assert {s["_resource"]["project_name"] for s in collector.spans()} == {"z-ai-test"}


def test_an_unreachable_collector_does_not_break_the_request(run_app):
    result = run_app("--scenario", "chat", "--prompt", "still works", fi_base_url="http://127.0.0.1:9")
    assert result.returncode == 0
    assert "RESULT chat: Z.ai stand-in reply to: still works" in result.stdout


def test_a_stream_that_ends_abnormally_is_not_an_error_span(run_app, collector):
    """Z.ai reports an inference that dies mid-stream through finish_reason, not an HTTP error, so the
    span ends OK, shows only the text that arrived, and does not record the finish reason."""
    result = run_app("--scenario", "stream", "--prompt", "[[abnormal-stream]] tell me more")
    assert result.returncode == 0, result.stderr[-1500:]
    (llm,) = llm_spans(collector)
    assert llm["status"]["code"] == "STATUS_CODE_OK"
    assert llm["_attrs"]["output.value"] == "Z.ai stand-in"
    assert "network_error" not in "\n".join(collector.raw_texts())
