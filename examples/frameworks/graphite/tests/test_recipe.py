"""Contract tests: what Graphite's spans look like when they reach a Future AGI collector.

Each test runs ../app.py in a separate process against a fake model endpoint and a
recording collector, so the real grafi package, the real OpenTelemetry SDK and the real
OTLP/HTTP exporter are in the path.
"""

from __future__ import annotations

import importlib.metadata

import pytest
from conftest import FI_API_KEY, FI_SECRET_KEY, MARKER, by_name, free_port


def run_ok(run_app, collector, scenario="chat", **kwargs):
    done = run_app(scenario, **kwargs)
    assert done.returncode == 0, done.stdout + done.stderr
    return done, collector.spans()


def kinds(spans):
    return {s["name"]: s["_attrs"].get("fi.span.kind") for s in spans}


def test_hierarchy_and_kinds(run_app, collector):
    """AC-07, AC-03: assistant -> workflow -> node -> tool, one trace, Graphite's own span kinds."""
    done, spans = run_ok(run_app, collector)
    assert "status=ok" in done.stdout
    assert len({s["trace_id"] for s in spans}) == 1

    by_id = {s["span_id"]: s for s in spans}
    assistant = by_name(spans, "WeatherAssistant.run")
    workflow = by_name(spans, "tool_workflow.invoke")
    nodes = by_name(spans, "LLMNode.invoke") + by_name(spans, "ToolNode.invoke")
    llm = by_name(spans, "ChatLLM.invoke")
    tool = by_name(spans, "WeatherTool.invoke")
    assert (len(assistant), len(workflow), len(nodes), len(llm), len(tool)) == (1, 1, 3, 2, 1)
    assert "parent_span_id" not in assistant[0]  # the root
    assert workflow[0]["parent_span_id"] == assistant[0]["span_id"]
    assert all(n["parent_span_id"] == workflow[0]["span_id"] for n in nodes)
    assert all(by_id[s["parent_span_id"]]["name"] == "LLMNode.invoke" for s in llm)
    assert by_id[tool[0]["parent_span_id"]]["name"] == "ToolNode.invoke"

    assert {s["_attrs"]["fi.span.kind"] for s in assistant + workflow} == {"AGENT"}
    assert {s["_attrs"]["fi.span.kind"] for s in nodes} == {"CHAIN"}
    assert {s["_attrs"]["fi.span.kind"] for s in llm} == {"LLM"}
    assert tool[0]["_attrs"]["fi.span.kind"] == "TOOL"
    assert all("oi_span_type" not in s["_attrs"] for s in spans)


def test_session_is_the_conversation_id(run_app, collector):
    """AC-04."""
    _, spans = run_ok(run_app, collector)
    assert {s["_attrs"]["session.id"] for s in spans} == {"graphite-tracing-demo"}
    assert all("conversation_id" not in s["_attrs"] for s in spans)


def test_empty_ids_are_not_exported(run_app, collector):
    """AC-06: Graphite writes "" when the application sets no user id; that is not an id."""
    _, spans = run_ok(run_app, collector, env={"APP_CONVERSATION": ""})
    assert all("user.id" not in s["_attrs"] and "user_id" not in s["_attrs"] for s in spans)
    assert all("session.id" not in s["_attrs"] and "conversation_id" not in s["_attrs"] for s in spans)


def test_user_id_when_the_application_sets_one(run_app, collector):
    _, spans = run_ok(run_app, collector, env={"APP_USER_ID": "user-77"})
    assert {s["_attrs"]["user.id"] for s in spans} == {"user-77"}
    assert all("user_id" not in s["_attrs"] for s in spans)


def test_dict_valued_attribute_does_not_break_export(run_app, collector):
    """AC-05: InvokeContext.kwargs is a dict and Graphite copies it onto every span."""
    done, spans = run_ok(run_app, collector, env={"APP_KWARGS": MARKER})
    assert "status=ok" in done.stdout
    assert len(spans) == 8
    assert all("kwargs" not in s["_attrs"] for s in spans)
    assert all(not isinstance(v, dict) for s in spans for v in s["_attrs"].values())


def test_authentication_endpoint_resource_and_no_gzip(run_app, collector):
    run_ok(run_app, collector, env={"OTEL_EXPORTER_OTLP_COMPRESSION": "gzip", "OTEL_EXPORTER_OTLP_TRACES_COMPRESSION": "gzip"})
    assert collector.exports
    for export in collector.exports:
        assert export["path"] == "/tracer/v1/traces"
        assert export["headers"]["x-api-key"] == FI_API_KEY
        assert export["headers"]["x-secret-key"] == FI_SECRET_KEY
        assert "content-encoding" not in export["headers"], "the recipe sends uncompressed bodies"
        assert export["headers"]["content-type"] == "application/x-protobuf"
    for span in collector.spans():
        assert span["_resource"]["project_name"] == "graphite-test"
        assert span["_resource"]["project_type"] == "observe"
        assert span["_scope"]["name"] == "grafi"


def test_tool_error_marks_the_chain_as_error(run_app, collector):
    done, spans = run_ok(run_app, collector, "tool-error")
    assert "status=error" in done.stdout
    status = {s["name"]: s.get("status", {}).get("code") for s in spans}
    assert status["WeatherTool.invoke"] == "STATUS_CODE_ERROR"
    assert status["ToolNode.invoke"] == "STATUS_CODE_ERROR"
    assert status["tool_workflow.invoke"] == "STATUS_CODE_ERROR"
    assert status["WeatherAssistant.run"] == "STATUS_CODE_ERROR"
    assert status["ChatLLM.invoke"] != "STATUS_CODE_ERROR", "the model call itself succeeded"
    tool = by_name(spans, "WeatherTool.invoke")[0]
    assert tool["_attrs"]["error.type"] == "FunctionCallException"


def test_model_error_marks_the_llm_span_as_error(run_app, collector):
    done, spans = run_ok(run_app, collector, "model-error")
    assert "status=error" in done.stdout
    llm = by_name(spans, "ChatLLM.invoke")
    assert [s["status"]["code"] for s in llm] == ["STATUS_CODE_ERROR"]
    assert llm[0]["_attrs"]["error.type"] == "LLMToolException"
    assert llm[0]["_attrs"]["fi.span.kind"] == "LLM"


def test_spans_are_flushed_at_exit_without_an_explicit_shutdown(run_app, collector):
    """The batch processor registers an atexit hook; provider.shutdown() is still the documented call."""
    _, spans = run_ok(run_app, collector, env={"APP_NO_SHUTDOWN": "1"})
    assert len(spans) == 8


def test_a_dead_collector_does_not_break_the_application(run_app, collector):
    done = run_app("chat", fi_base_url=f"http://127.0.0.1:{free_port()}")
    assert done.returncode == 0, done.stderr
    assert "status=ok" in done.stdout
    assert not collector.exports


def test_missing_keys_fail_with_a_clear_message(run_app, collector):
    done = run_app("chat", env={"FI_SECRET_KEY": ""})
    assert done.returncode != 0
    assert "Set FI_API_KEY and FI_SECRET_KEY" in done.stderr


def test_two_projects_are_kept_apart(run_app, collector):
    """Each export carries the project it was configured with; nothing is shared between processes."""
    run_ok(run_app, collector, env={"FI_PROJECT_NAME": "tenant-a", "APP_CONVERSATION": "conv-a"})
    run_ok(run_app, collector, env={"FI_PROJECT_NAME": "tenant-b", "APP_CONVERSATION": "conv-b"})
    seen = {(s["_resource"]["project_name"], s["_attrs"]["session.id"]) for s in collector.spans()}
    assert seen == {("tenant-a", "conv-a"), ("tenant-b", "conv-b")}


def test_the_provider_instrumentor_adds_a_second_llm_span_with_model_and_tokens(run_app, collector):
    """J7: optional. Graphite's own LLM span has no model or tokens; the OpenInference OpenAI
    instrumentor adds a child span that has them (and a second span of kind LLM)."""
    _, spans = run_ok(run_app, collector, env={"GRAFI_PROVIDER_SPANS": "1"})
    by_id = {s["span_id"]: s for s in spans}
    provider_spans = [s for s in spans if s["_attrs"].get("openinference.span.kind") == "LLM"]
    assert len(provider_spans) == 2
    for span in provider_spans:
        assert by_id[span["parent_span_id"]]["name"] == "ChatLLM.invoke"
        assert span["_attrs"]["llm.model_name"] == "fake-model"
        assert span["_attrs"]["llm.token_count.total"] == 38
    graphite_llm = by_name(spans, "ChatLLM.invoke")
    assert all("llm.model_name" not in s["_attrs"] for s in graphite_llm)


def test_versions_are_recorded():
    """Printed with -v in the evidence logs."""
    print("grafi", importlib.metadata.version("grafi"))
    print("opentelemetry-sdk", importlib.metadata.version("opentelemetry-sdk"))
    assert importlib.metadata.version("grafi")


@pytest.mark.parametrize("scenario", ["chat", "tool-error", "model-error"])
def test_every_span_has_a_kind_and_a_name(run_app, collector, scenario):
    _, spans = run_ok(run_app, collector, scenario)
    assert spans
    assert all(s["_attrs"].get("fi.span.kind") in {"AGENT", "CHAIN", "LLM", "TOOL"} for s in spans)
