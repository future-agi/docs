"""agent.py with the real SDK tracer and a scripted model: the span tree and attributes the page describes.

No network: the model is replaced and spans are read from an in-memory exporter added to the
SDK's own TracerProvider.
"""
import base64
import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import agent
from ibm_watsonx_orchestrate_sdk.client import Client
from ibm_watsonx_orchestrate_sdk.observability import TracerConfig

EXPORTER = InMemorySpanExporter()
agent.tracer._provider.add_span_processor(SimpleSpanProcessor(EXPORTER))


class ScriptedModel:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def invoke(self, messages):
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def reply(content="", tool_calls=()):
    return AIMessage(content=content, tool_calls=list(tool_calls),
                     usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
                     response_metadata={"model_name": "scripted-model"})


@pytest.fixture
def spans(monkeypatch):
    EXPORTER.clear()

    def run(model, question):
        monkeypatch.setattr(agent, "llm", model)
        return agent.ask(question, conversation_id="conv-1")  # SimpleSpanProcessor: spans are exported on end

    return run


def by_name(finished):
    out = {}
    for s in finished:
        out.setdefault(s.name, []).append(s)
    return out


def test_answer_with_a_failed_tool_call_is_one_trace(spans):
    model = ScriptedModel(
        reply(tool_calls=[{"name": "get_weather", "args": {"city": "Paris"}, "id": "c1"},
                          {"name": "get_weather", "args": {"city": "Atlantis"}, "id": "c2"}]),
        reply("Paris: 18 C, light rain. No station for Atlantis."),
    )
    answer = spans(model, "Weather in Paris and Atlantis?")
    assert answer.startswith("Paris")
    finished = EXPORTER.get_finished_spans()
    names = by_name(finished)
    assert {k: len(v) for k, v in names.items()} == {"weather-agent": 1, "agent_node": 2, "chat_model": 2, "get_weather": 2}
    assert len({s.context.trace_id for s in finished}) == 1

    root = names["weather-agent"][0]
    assert root.parent is None
    assert root.attributes["span.kind"] == "root"
    assert root.attributes["conversation.id"] == "conv-1"
    assert root.attributes["input.value"] == "Weather in Paris and Atlantis?"
    assert root.attributes["output.value"] == answer
    assert root.status.status_code != StatusCode.ERROR

    agents = {s.context.span_id for s in names["agent_node"]}
    for s in names["agent_node"] + names["get_weather"]:
        assert s.parent.span_id == root.context.span_id
    for s in names["chat_model"]:
        assert s.parent.span_id in agents
        assert s.attributes["span.kind"] == "llm"
        assert s.attributes["gen_ai.request.model"] == agent.MODEL
        assert s.attributes["llm.provider"] == "openai"
        assert (s.attributes["llm.usage.prompt_tokens"], s.attributes["llm.usage.completion_tokens"]) == (120, 30)
    assert {s.attributes["span.kind"] for s in names["agent_node"]} == {"agent"}

    tools = sorted(names["get_weather"], key=lambda s: s.status.status_code == StatusCode.ERROR)
    ok, failed = tools
    assert ok.attributes["tool.name"] == "get_weather" and ok.attributes["span.kind"] == "tool"
    assert json.loads(ok.attributes["input.value"]) == {"city": "Paris"}
    assert failed.status.status_code == StatusCode.ERROR
    assert "Atlantis" in failed.status.description  # raw error text: the collector replaces it with "error"
    event = failed.events[0]
    assert event.name == "exception" and "exception.stacktrace" in event.attributes  # the collector removes it

    # The SDK writes this placeholder on every span when no user is known; the collector drops it.
    assert {s.attributes["user.id"] for s in finished} == {"Unknown User"}
    # handle_tool_errors=True: the failed call went back to the model as an error ToolMessage.
    assert any(isinstance(m, ToolMessage) and m.status == "error" for m in model.seen[1])


def test_a_failed_model_call_fails_the_run_and_every_span_on_its_path(spans):
    with pytest.raises(RuntimeError, match="model unavailable"):
        spans(ScriptedModel(RuntimeError("model unavailable")), "Weather in Paris?")
    names = by_name(EXPORTER.get_finished_spans())
    assert set(names) == {"weather-agent", "agent_node", "chat_model"}
    for name in names:
        assert names[name][0].status.status_code == StatusCode.ERROR


def test_without_a_client_the_sdk_sends_no_auth_header_and_no_project_name():
    config = TracerConfig()
    assert config.endpoint == "http://127.0.0.1:1/v1/traces"  # from WXO_OTLP_ENDPOINT (conftest)
    assert config.get_auth_headers() == {}
    resource = dict(agent.tracer._provider.resource.attributes)
    assert resource["service.name"] == "weather-agent"
    assert "project_name" not in resource


def test_a_client_mode_tracer_sends_a_bearer_token_and_ids_from_it():
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    token = ".".join([b64({"alg": "none"}), b64({"tenant_id": "t-1", "idpUniqueId": "someone@example.com"}), "sig"])
    config = TracerConfig(
        client=Client(api_key=token, instance_url="http://127.0.0.1:9", local=True),
        agent_id="a-1", workspace_id="w-1", trace_injection_path="http://collector:4318/v1/traces",
    )
    assert config.endpoint == "http://collector:4318/v1/traces"
    assert config.get_auth_headers() == {"Authorization": f"Bearer {token}"}
    assert (config.tenant_id, config.user_id) == ("t-1", "someone@example.com")
    assert config.build_resource_attributes() == {
        "tenant.id": "t-1", "agent.id": "a-1", "workspace.id": "w-1", "environment.name": "live"}
