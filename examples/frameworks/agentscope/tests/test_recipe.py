"""The recipe as a customer runs it: app.py in its own process, real AgentScope, a fake
OpenAI endpoint and a recording collector. No Future AGI stack is needed."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from conftest import FI_API_KEY, FI_SECRET_KEY, MODEL_KEY, ROOT, by_name

CONTENT_ON = {"FI_CAPTURE_CONTENT": "1"}


def spans_of(collector):
    spans = collector.spans()
    assert spans, "no spans reached the collector"
    return spans


def tree(spans):
    agent = by_name(spans, "invoke_agent")
    chats = by_name(spans, "chat ")
    tools = by_name(spans, "execute_tool")
    return agent, chats, tools


@pytest.mark.parametrize("scenario", ["chat", "nostream"])
def test_tool_round_trip_hierarchy_model_and_tokens(run_app, collector, scenario):
    out = run_app(scenario)
    assert out.returncode == 0, out.stderr
    assert "Answer:" in out.stdout

    spans = spans_of(collector)
    agent, chats, tools = tree(spans)
    assert [len(agent), len(chats), len(tools)] == [1, 2, 1]
    assert len({s["trace_id"] for s in spans}) == 1, "one trace id for the whole reply"

    root = agent[0]
    assert "parent_span_id" not in root or not root["parent_span_id"]
    for child in chats + tools:
        assert child["parent_span_id"] == root["span_id"], "model and tool spans are children of the reply span"

    for chat in chats:
        attrs = chat["_attrs"]
        assert attrs["gen_ai.operation.name"] == "chat"
        assert attrs["gen_ai.request.model"] == "fake-model"
        assert attrs["gen_ai.provider.name"] == "openai"
        assert attrs["gen_ai.usage.input_tokens"] == 31
        assert attrs["gen_ai.usage.output_tokens"] == 7
    assert tools[0]["_attrs"]["gen_ai.tool.name"] == "get_weather"
    assert tools[0]["_attrs"]["gen_ai.operation.name"] == "execute_tool"
    assert root["_attrs"]["gen_ai.agent.name"] == "support-agent"
    assert {s["_attrs"]["gen_ai.conversation.id"] for s in spans} == {"support-chat-42"}
    assert all(s["_scope"]["name"] == "agentscope" for s in spans)


def test_every_span_status_is_ok_on_success(run_app, collector):
    assert run_app("chat").returncode == 0
    assert {s["status"]["code"] for s in spans_of(collector)} == {"STATUS_CODE_OK"}


def test_request_shape_matches_the_collector_contract(run_app, collector):
    assert run_app("chat").returncode == 0
    assert collector.exports, "nothing exported"
    for export in collector.exports:
        assert export["path"] == "/tracer/v1/traces", "traces only, on the documented path"
        assert export["headers"].get("content-encoding") in (None, "identity"), "the recipe sends uncompressed bodies"
        assert export["headers"]["x-api-key"] == FI_API_KEY
        assert export["headers"]["x-secret-key"] == FI_SECRET_KEY
        assert "authorization" not in export["headers"]
    for span in collector.spans():
        assert span["_resource"]["project_name"] == "agentscope-test"
        assert span["_resource"]["project_type"] == "observe"
        assert "project_name" not in span["_attrs"], "project_name belongs on the resource, not on a span"


def test_gzip_requested_by_environment_is_not_used(run_app, collector):
    out = run_app(
        "chat",
        env={"OTEL_EXPORTER_OTLP_COMPRESSION": "gzip", "OTEL_EXPORTER_OTLP_TRACES_COMPRESSION": "gzip"},
    )
    assert out.returncode == 0, out.stderr
    assert collector.exports
    assert all(e["headers"].get("content-encoding") in (None, "identity") for e in collector.exports)


def test_model_failure_marks_model_and_reply_spans_error(run_app, collector):
    out = run_app("model-error", env=CONTENT_ON)
    assert out.returncode == 1
    spans = spans_of(collector)
    agent, chats, tools = tree(spans)
    assert [len(agent), len(chats), len(tools)] == [1, 1, 0]
    assert agent[0]["status"]["code"] == chats[0]["status"]["code"] == "STATUS_CODE_ERROR"
    assert chats[0]["parent_span_id"] == agent[0]["span_id"]
    assert len({s["trace_id"] for s in spans}) == 1, "the failed reply is still exported"
    assert chats[0]["_attrs"]["gen_ai.request.model"] == "model-that-does-not-exist"
    assert "gen_ai.usage.input_tokens" not in chats[0]["_attrs"], "no usage is invented for a failed call"


def test_tool_exception_does_not_fail_the_tool_span(run_app, collector):
    """Pins upstream behaviour the docs page states: AgentScope turns a tool exception into an
    error tool result for the model, so the span is not ERROR. With content on, the failure is
    visible in the span's result attribute."""
    out = run_app("tool-error", env=CONTENT_ON)
    assert out.returncode == 0, out.stderr
    spans = spans_of(collector)
    _, _, tools = tree(spans)
    assert tools[0]["status"]["code"] == "STATUS_CODE_OK"
    assert "ToolResultState.ERROR" in tools[0]["_attrs"]["gen_ai.tool.call.result"]
    assert not tools[0].get("events")


def _clean_env(model, collector, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OPENAI", "OTEL_"))}
    env.update(
        OPENAI_API_KEY=MODEL_KEY,
        OPENAI_BASE_URL=model.url,
        FI_API_KEY=FI_API_KEY,
        FI_SECRET_KEY=FI_SECRET_KEY,
        FI_BASE_URL=collector.url,
        OTEL_EXPORTER_OTLP_TRACES_TIMEOUT="3",
    )
    env.update(extra)
    return env


def _python(code, env):
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


def test_flush_on_normal_exit_without_an_explicit_flush(collector, model):
    """A script that never calls force_flush still exports: the provider flushes at exit."""
    code = (
        f"import asyncio, sys\nsys.path.insert(0, {str(ROOT)!r})\n"
        "import app, futureagi_tracing\n"
        "futureagi_tracing.setup_tracing()\n"
        "asyncio.run(app.run('chat', 'hi', 'sys'))\n"
    )
    out = _python(code, _clean_env(model, collector))
    assert out.returncode == 0, out.stderr
    assert len(collector.spans()) == 4


def test_provider_installed_after_the_agent_is_built_still_traces(collector, model):
    """TracingMiddleware looks the provider up on every call, so the order of agent
    construction and provider setup does not matter. What matters is that the provider
    exists before the first reply."""
    code = (
        "import asyncio, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import app, futureagi_tracing\n"
        "from agentscope.message import UserMsg\n"
        "agent = app.build_agent('chat', 'sys')\n"
        "futureagi_tracing.setup_tracing()\n"
        "asyncio.run(agent.reply(UserMsg(name='user', content='hi')))\n"
    )
    out = _python(code, _clean_env(model, collector))
    assert out.returncode == 0, out.stderr
    assert len(collector.spans()) == 4


def test_unreachable_collector_does_not_fail_the_agent(run_app):
    out = run_app("chat", fi_base_url="http://127.0.0.1:9")
    assert out.returncode == 0, out.stderr
    assert "Answer:" in out.stdout


def test_no_provider_means_no_spans_and_no_failure(collector, model):
    """Without a tracer provider TracingMiddleware is a no-op. This is what a 2.x user who
    only called agentscope.init sees: the agent works and nothing is exported."""
    code = (
        "import asyncio, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import app\n"
        "print(asyncio.run(app.run('chat', 'hi', 'sys')))\n"
    )
    out = _python(code, _clean_env(model, collector))
    assert out.returncode == 0, out.stderr
    assert "Answer:" in out.stdout
    assert collector.exports == []


def test_two_projects_stay_apart(run_app, collector):
    assert run_app("chat", env={"FI_PROJECT_NAME": "project-a"}).returncode == 0
    assert run_app("chat", env={"FI_PROJECT_NAME": "project-b"}).returncode == 0
    spans = spans_of(collector)
    by_project = {}
    for span in spans:
        by_project.setdefault(span["_resource"]["project_name"], set()).add(span["trace_id"])
    assert set(by_project) == {"project-a", "project-b"}
    assert not (by_project["project-a"] & by_project["project-b"])


def test_credentials_stay_where_they_belong(run_app, collector, model):
    assert run_app("chat", env=CONTENT_ON).returncode == 0
    everything = collector.everything()
    # the model key is only ever sent to the model, the Future AGI keys only to the collector
    assert MODEL_KEY not in everything
    for key in (FI_API_KEY, FI_SECRET_KEY):
        assert key not in "".join(e["body"].decode("utf-8", "replace") for e in collector.exports)
    sent_to_model = "".join(str(r["body"]) + str(r["auth"]) for r in model.requests)
    assert FI_API_KEY not in sent_to_model and FI_SECRET_KEY not in sent_to_model
