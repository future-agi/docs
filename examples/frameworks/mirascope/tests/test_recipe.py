"""What the recipe sends, and what Mirascope 2.5.0 actually emits (observed, not assumed).

Every test runs app.py in a subprocess against a fake model and a recording OTLP/HTTP receiver.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import FI_API_KEY, FI_SECRET_KEY, HERE, MARKER, MODEL_API_KEY, MODEL_ID

OK, ERROR = 0, 2  # SPAN_STATUS_CODE_UNSET / SPAN_STATUS_CODE_ERROR
CLIENT, INTERNAL = 3, 1


def test_scenario_runs_and_flushes(runs):
    run = runs("chat")
    assert run.returncode == 0, run.stderr
    assert '"ok": true' in run.stdout
    # The process exited right after the call; the batch still arrived (provider.shutdown()).
    assert len(run.spans) == 1


def test_wire_format(runs):
    run = runs("chat")
    request = run.received[0]
    assert request["path"] == "/tracer/v1/traces"
    assert request["headers"]["x-api-key"] == FI_API_KEY
    assert request["headers"]["x-secret-key"] == FI_SECRET_KEY
    assert request["headers"]["content-type"] == "application/x-protobuf"
    assert "content-encoding" not in request["headers"], "the Future AGI collector rejects gzip"


def test_resource_names_the_project(runs):
    resource = runs("chat", project="my-chatbot").spans[0]["resource"]
    assert resource["project_name"] == "my-chatbot"
    assert resource["project_type"] == "observe"


def test_two_projects_stay_apart(runs):
    a = runs("chat", project="project-a").spans[0]["resource"]["project_name"]
    b = runs("chat", project="project-b").spans[0]["resource"]["project_name"]
    assert (a, b) == ("project-a", "project-b")


def test_chat_span(runs):
    run = runs("chat")
    span = run.span("chat ")
    assert span["name"] == f"chat {MODEL_ID}"
    assert span["kind"] == CLIENT
    assert span["status_code"] == OK
    assert span["parent_span_id"] == ""
    attrs = span["attributes"]
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert attrs["gen_ai.request.model"] == MODEL_ID
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 7
    assert run.span("chat ")["scope"] == "mirascope.llm"


def test_the_model_provider_key_goes_to_the_model_only(runs):
    run = runs("chat", capture_content=True)
    assert run.model_requests[0]["authorization"] == f"Bearer {MODEL_API_KEY}"
    for key in (MODEL_API_KEY, FI_API_KEY, FI_SECRET_KEY):
        assert key not in run.everything()


def test_tool_loop_without_a_wrapper_is_three_traces(runs):
    """Observed: Mirascope emits no span for running a tool, and each step of the loop is a root."""
    run = runs("tool")
    names = sorted(s["name"].split(" ")[0] for s in run.spans)
    assert names == ["Response.resume", "chat", "chat", "execute_tool"]
    assert len({s["trace_id"] for s in run.spans}) == 3
    resume = run.span("Response.resume")
    second_chat = [s for s in run.spans if s["parent_span_id"] == resume["span_id"]]
    assert [s["name"].split(" ")[0] for s in second_chat] == ["chat"]


def test_tool_loop_inside_ops_trace_is_one_trace(runs):
    run = runs("agent")
    assert len({s["trace_id"] for s in run.spans}) == 1
    root = run.span("weather_agent")
    assert root["parent_span_id"] == ""
    by_id = {s["span_id"]: s for s in run.spans}
    tool = run.span("execute_tool get_weather")
    assert by_id[tool["parent_span_id"]] is root
    resume = run.span("Response.resume")
    assert by_id[resume["parent_span_id"]] is root
    chats = [s for s in run.spans if s["name"].startswith("chat ")]
    assert len(chats) == 2
    assert {by_id[c["parent_span_id"]]["name"].split(" ")[0] for c in chats} == {"weather_agent", "Response.resume"}


def test_tool_span_is_the_apps_own(runs):
    tool = runs("agent").span("execute_tool get_weather")
    assert tool["scope"] == "mirascope.ops"
    assert tool["attributes"]["gen_ai.operation.name"] == "execute_tool"
    assert tool["attributes"]["gen_ai.tool.name"] == "get_weather"


def test_stream_is_one_span_with_usage(runs):
    run = runs("stream")
    assert [s["name"] for s in run.spans] == [f"chat {MODEL_ID}"]
    attrs = run.spans[0]["attributes"]
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 7


def test_error_is_an_error_span(runs):
    run = runs("error")
    assert '"ok": false' in run.stdout
    span = run.spans[0]
    assert span["status_code"] == ERROR
    assert span["attributes"]["error.type"] == "NotFoundError"
    assert any(e["name"] == "exception" for e in span["events"])
    assert "gen_ai.usage.input_tokens" not in span["attributes"]


def test_a_reply_without_usage_stores_no_token_attributes(runs):
    run = runs("chat", usage=False)
    attrs = run.spans[0]["attributes"]
    assert run.returncode == 0
    assert not [k for k in attrs if "token" in k or "usage" in k], attrs


def test_session_id_and_function_names_are_kept(runs):
    run = runs("trace")
    assert len({s["trace_id"] for s in run.spans}) == 1
    plan = run.span("plan")
    assert plan["attributes"]["mirascope.ops.session.id"] == "mirascope-demo-session"
    summarize = run.span("summarize")
    assert summarize["attributes"]["mirascope.fn.qualname"] == "summarize"
    chat = run.span("chat ")
    assert chat["parent_span_id"] == summarize["span_id"]


def test_the_example_never_uses_the_langfuse_decorator():
    """The Langfuse decorator is a different path (PRD AC-02)."""
    for path in HERE.glob("*.py"):
        source = path.read_text()
        assert "integrations.langfuse" not in source, path
        assert "with_langfuse" not in source.replace("not with_langfuse", ""), path


def test_exporter_is_http_not_grpc():
    source = (HERE / "futureagi_tracing.py").read_text()
    assert "proto.http.trace_exporter" in source
    assert "proto.grpc" not in source
    assert "Compression.NoCompression" in source


def test_missing_keys_fail_fast():
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-c", "from futureagi_tracing import build_tracer_provider as b; b()"],
        cwd=HERE,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(HERE)},
        capture_output=True,
        text=True,
    )
    assert done.returncode != 0
    assert "FI_API_KEY" in done.stderr


def test_request_parameters_are_kept_and_stop_sequences_are_not():
    from conftest import run_code

    run = run_code(
        "from mirascope import llm, ops\n"
        "from futureagi_tracing import build_tracer_provider\n"
        "provider = build_tracer_provider()\n"
        "ops.configure(tracer_provider=provider)\n"
        "ops.instrument_llm()\n"
        f"llm.Model({MODEL_ID!r}, temperature=0.2, max_tokens=50, top_p=0.9, stop=['END']).call('hi')\n"
        "provider.shutdown()\n",
    )
    assert run.returncode == 0, run.stderr
    attrs = run.spans[0]["attributes"]
    assert attrs["gen_ai.request.temperature"] == 0.2
    assert attrs["gen_ai.request.max_tokens"] == 50
    assert attrs["gen_ai.request.top_p"] == 0.9
    assert "gen_ai.request.stop_sequences" not in attrs  # not on the list; content-off drops it


def test_configure_before_instrument_is_enforced_by_mirascope():
    from conftest import run_code

    run = run_code("from mirascope import ops\nops.instrument_llm()\n")
    assert run.returncode != 0
    assert "You must call `configure()` before calling `instrument_llm()`" in run.stderr


def test_a_model_id_without_a_suffix_goes_to_the_responses_api(runs):
    from conftest import run_code

    run = run_code(
        "from mirascope import llm\n"
        "try:\n"
        "    llm.Model('openai/fake-model').call('hi')\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
    )
    assert [r["path"] for r in run.model_requests] == ["/v1/responses"]
    assert [r["path"] for r in runs("chat").model_requests] == ["/v1/chat/completions"]


def test_a_normal_exit_flushes_without_shutdown_but_os_exit_does_not():
    from conftest import run_code

    prelude = (
        "from mirascope import llm, ops\n"
        "from futureagi_tracing import build_tracer_provider\n"
        "provider = build_tracer_provider()\n"
        "ops.configure(tracer_provider=provider)\n"
        "ops.instrument_llm()\n"
        f"llm.Model({MODEL_ID!r}).call('hi')\n"
    )
    assert len(run_code(prelude).spans) == 1, "the SDK flushes at a normal interpreter exit"
    assert len(run_code(prelude + "import os\nos._exit(0)\n").spans) == 0
    assert len(run_code(prelude + "import os\nprovider.shutdown()\nos._exit(0)\n").spans) == 1
