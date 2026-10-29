"""The recorded fixtures (real model, content hidden or masked) keep the shape the page describes.

* ``agentspec-26.3.1-langgraph-traceai.otlp.json``: this recipe.
* ``agentspec-26.3.1-langgraph-openinference-0.1.15.otlp.json``: Arize's Agent Spec
  instrumentor on the Future AGI provider, for the comparison on the page.

Both are OTLP/JSON export requests with lower-case hex ids, as the Future AGI collector
reads them. ``scripts/replay_fixture.py`` posts either one to a Future AGI project.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TRACEAI = FIXTURES / "agentspec-26.3.1-langgraph-traceai.otlp.json"
OPENINFERENCE = FIXTURES / "agentspec-26.3.1-langgraph-openinference-0.1.15.otlp.json"
HEX = {"traceId": re.compile(r"[0-9a-f]{32}"), "spanId": re.compile(r"[0-9a-f]{16}"),
       "parentSpanId": re.compile(r"[0-9a-f]{16}")}


def value(v: dict):
    return next(iter(v.values())) if v else None


def spans_of(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for rs in payload["resourceSpans"]:
        resource = {a["key"]: value(a["value"]) for a in rs["resource"]["attributes"]}
        for ss in rs["scopeSpans"]:
            for span in ss["spans"]:
                attrs = {a["key"]: value(a["value"]) for a in span.get("attributes", [])}
                out.append({**span, "attrs": attrs, "resource": resource})
    return out


@pytest.mark.parametrize("path", [TRACEAI, OPENINFERENCE], ids=["traceai", "openinference"])
def test_one_trace_hex_ids_and_project(path):
    spans = spans_of(path)
    assert len({s["traceId"] for s in spans}) == 1
    for span in spans:
        for field, pattern in HEX.items():
            if span.get(field):
                assert pattern.fullmatch(span[field]), (field, span[field])
        assert span["resource"]["project_name"] == "open-agent-spec-fixture"
    text = path.read_text(encoding="utf-8")
    for needle in ("Lisbon", "MARK-", "fixture-api-key", "fixture-secret-key", "127.0.0.1", "/Users/", "/home/"):
        assert needle not in text, needle


def test_traceai_fixture_tree_model_and_tokens():
    spans = spans_of(TRACEAI)
    by_id = {s["spanId"]: s for s in spans}
    root = [s for s in spans if not s.get("parentSpanId")]
    assert [r["name"] for r in root] == ["weather_assistant"]
    kinds = sorted(s["attrs"].get("gen_ai.span.kind") for s in spans)
    assert kinds == ["CHAIN"] * 4 + ["LLM"] * 2 + ["TOOL"]
    for llm in (s for s in spans if s["attrs"].get("gen_ai.span.kind") == "LLM"):
        assert llm["attrs"]["gen_ai.request.model"] == "gpt-6-luna"
        assert int(llm["attrs"]["gen_ai.usage.input_tokens"]) > 0
        assert int(llm["attrs"]["gen_ai.usage.output_tokens"]) > 0
        assert by_id[llm["parentSpanId"]]["name"] == "model"
    assert by_id[[s for s in spans if s["name"] == "get_weather"][0]["parentSpanId"]]["name"] == "tools"
    assert all(s["attrs"].get("input.value") in (None, "__REDACTED__") for s in spans)


def test_openinference_fixture_agent_spec_names_no_tokens():
    spans = spans_of(OPENINFERENCE)
    names = sorted(s["name"] for s in spans)
    assert names == ["AgentExecution[weather_assistant]", "LlmGenerationSpan", "LlmGenerationSpan",
                     "RootSpan", "ToolExecution[get_weather]"]
    kinds = {s["name"]: s["attrs"].get("openinference.span.kind") for s in spans}
    assert kinds["AgentExecution[weather_assistant]"] == "AGENT"
    assert kinds["ToolExecution[get_weather]"] == "TOOL"
    assert kinds["RootSpan"] == "CHAIN"
    for llm in (s for s in spans if s["name"] == "LlmGenerationSpan"):
        assert llm["attrs"]["openinference.span.kind"] == "LLM"
        assert llm["attrs"]["llm.model_name"] == "gpt-6-luna"
        # The LangGraph adapter leaves the token counts empty; the instrumentor writes "null".
        assert llm["attrs"]["llm.token_count.prompt"] == "null"
        assert llm["attrs"]["llm.token_count.completion"] == "null"
    # Masked, but the agent definition (system prompt, model endpoint) is still exported.
    agent = [s for s in spans if s["name"].startswith("AgentExecution")][0]
    assert agent["attrs"]["agent.system_prompt"].startswith("You are a weather assistant")
    assert agent["attrs"]["agent.llm_config.url"] == "http://localhost:8000/v1"
