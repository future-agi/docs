"""The recipe end to end, hermetically: what reaches the wire for each scenario."""

from __future__ import annotations

import sys

import pytest

from conftest import by_name, kind

QUESTION = "What is the weather in Lisbon right now?"


def ancestors_reach(span: dict, root_id: str, index: dict) -> bool:
    seen = set()
    while span["parentSpanId"] and span["spanId"] not in seen:
        seen.add(span["spanId"])
        if span["parentSpanId"] == root_id:
            return True
        span = index.get(span["parentSpanId"], {"parentSpanId": "", "spanId": ""})
    return False


ASYNC_SPLITS_ON_PY310 = pytest.mark.xfail(
    sys.version_info < (3, 11),
    strict=True,
    reason="Python 3.10: LangChain cannot carry the run context into asyncio tasks, so each "
    "model call of an ainvoke() run is its own trace (plain LangGraph create_agent does the same)",
)


@pytest.mark.parametrize("scenario", ["chat", pytest.param("async", marks=ASYNC_SPLITS_ON_PY310)])
def test_one_trace_agent_root_llm_and_tool_children(run_app, scenario):
    run = run_app(scenario, QUESTION)
    assert run.returncode == 0, run.stderr[-2000:]
    spans = run.spans()
    assert len({s["traceId"] for s in spans}) == 1, "one agent run is one trace"

    roots = [s for s in spans if not s["parentSpanId"]]
    assert [r["name"] for r in roots] == ["weather_assistant"], "the Agent Spec agent name is the root"
    root = roots[0]
    assert kind(root) == "CHAIN"

    index = {s["spanId"]: s for s in spans}
    llms = [s for s in spans if kind(s) == "LLM"]
    tools = [s for s in spans if kind(s) == "TOOL"]
    assert len(llms) == 2, "tool call turn + answer turn"
    assert [t["name"] for t in tools] == ["get_weather"]
    for child in llms + tools:
        assert ancestors_reach(child, root["spanId"], index)

    for llm in llms:
        attrs = llm["attributes"]
        assert attrs["gen_ai.request.model"] == "fake-model"
        assert attrs["gen_ai.usage.input_tokens"] == 17
        assert attrs["gen_ai.usage.output_tokens"] == 5
    assert all(s["status"].get("code") != "STATUS_CODE_ERROR" for s in spans)


def test_exporter_contract_headers_resource_path(run_app):
    run = run_app("chat", QUESTION)
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.recorder.requests, "nothing exported"
    for request in run.recorder.requests:
        assert request["path"] == "/tracer/v1/traces"
        assert request["headers"]["x-api-key"] == run.env["FI_API_KEY"]
        assert request["headers"]["x-secret-key"] == run.env["FI_SECRET_KEY"]
        assert request["headers"].get("content-encoding", "") != "gzip"
        assert request["headers"]["content-type"] == "application/x-protobuf"
    for span in run.spans():
        assert span["resource"]["project_name"] == "oas-test"
        assert span["resource"]["project_type"] == "observe"
    raw = run.recorder.raw()
    for secret in ("FI_API_KEY", "FI_SECRET_KEY", "MODEL_API_KEY"):
        assert run.env[secret].encode() not in raw, f"{secret} leaked into a span"


def test_two_runs_in_one_process_are_two_traces(run_app):
    run = run_app("chat", QUESTION, APP_RUNS="2")
    assert run.returncode == 0, run.stderr[-2000:]
    spans = run.spans()
    assert len({s["traceId"] for s in spans}) == 2
    assert len([s for s in spans if not s["parentSpanId"]]) == 2


def test_tool_error_is_exported_as_error(run_app):
    run = run_app("tool-error", QUESTION)
    assert run.returncode == 1
    assert "RESULT error: RuntimeError" in run.stdout
    spans = run.spans()
    assert len({s["traceId"] for s in spans}) == 1
    tool = by_name(spans, "get_weather")[0]
    assert tool["status"]["code"] == "STATUS_CODE_ERROR"
    assert not tool["status"].get("message")
    assert any(event["attributes"].get("exception.type") == "RuntimeError" for event in tool["events"])
    root = [s for s in spans if not s["parentSpanId"]][0]
    assert root["status"]["code"] == "STATUS_CODE_ERROR"


def test_model_error_is_exported_as_error(run_app):
    run = run_app("model-error", QUESTION)
    assert run.returncode == 1
    assert "RESULT error: AuthenticationError" in run.stdout
    spans = run.spans()
    llm = [s for s in spans if kind(s) == "LLM"][0]
    assert llm["status"]["code"] == "STATUS_CODE_ERROR"
    assert not llm["status"].get("message")
    assert any(event["attributes"].get("exception.type") == "openai.AuthenticationError" for event in llm["events"])
    assert run.env["MODEL_BAD_API_KEY"].encode() not in run.recorder.raw()
