"""Privacy: what leaves the process by default, and what the documented opt-in adds.

A unique marker is placed in the system prompt, the user prompt, the tool arguments, the
tool result, the model's answer and the text of an error. The scans read every byte the
collector received."""

from __future__ import annotations

import asyncio
import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from conftest import MARKER, MODEL_KEY, by_name
from futureagi_tracing import METADATA_ATTRIBUTES, ContentFilterExporter

SYSTEM = f"You are a helpful assistant. Internal note {MARKER}-SYSTEM."
PROMPT = f"What is the weather? {MARKER}-USER"

# Attributes AgentScope 2.0.10 writes that can hold what was said or done. A release that
# adds an attribute to neither set fails test_every_attribute_is_classified until it is reviewed.
CONTENT_ATTRIBUTES = {
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.tool.definitions",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "gen_ai.agent.description",
    "gen_ai.tool.description",
    "gen_ai.request.stop_sequences",
}


def run_all_scenarios(run_app, model, extra_env=None):
    model.tool_arg = f"{MARKER}-TOOLARG"
    results = {}
    for scenario in ("chat", "nostream", "tool-error", "model-error"):
        results[scenario] = run_app(scenario, "--prompt", PROMPT, "--system", SYSTEM, env=extra_env)
    return results


def test_default_exports_no_content(run_app, collector, model, machine_identifiers):
    results = run_all_scenarios(run_app, model)
    assert [r.returncode for r in results.values()] == [0, 0, 0, 1], {k: v.stderr[-300:] for k, v in results.items()}
    # the application itself still got its full answer
    assert MARKER in results["chat"].stdout

    everything = collector.everything()
    assert collector.spans(), "nothing was exported"
    assert MARKER not in everything, "a prompt, answer, tool payload or error text left the process"
    for label, value in machine_identifiers.items():
        assert value not in everything, f"{label} left the process"
    assert "Traceback" not in everything and "site-packages" not in everything


def test_default_keeps_the_metadata_a_trace_needs(run_app, collector, model):
    run_all_scenarios(run_app, model)
    spans = collector.spans()
    for span in spans:
        assert set(span["_attrs"]) <= METADATA_ATTRIBUTES
        for event in span.get("events", []):
            assert event["name"] == "exception"
            assert {a["key"] for a in event["attributes"]} == {"exception.type"}

    chats = [s for s in by_name(spans, "chat fake-model") if s["status"]["code"] == "STATUS_CODE_OK"]
    assert chats and all(s["_attrs"]["gen_ai.usage.input_tokens"] == 31 for s in chats)
    assert by_name(spans, "execute_tool get_weather") and by_name(spans, "invoke_agent support-agent")

    failed = [s for s in spans if s["status"]["code"] == "STATUS_CODE_ERROR"]
    assert len(failed) == 2, "the model call and the reply that contained it"
    assert {s["status"].get("message") for s in failed} == {"openai.BadRequestError"}, "class name only, no error text"


def test_opt_in_exports_what_agentscope_records(run_app, collector, model, machine_identifiers):
    results = run_all_scenarios(run_app, model, {"FI_CAPTURE_CONTENT": "1"})
    assert [r.returncode for r in results.values()] == [0, 0, 0, 1]
    spans = collector.spans()

    agent = by_name(spans, "invoke_agent")
    assert any(f"{MARKER}-USER" in s["_attrs"].get("gen_ai.input.messages", "") for s in agent)
    assert any(f"{MARKER}-TOOLARG" in s["_attrs"].get("gen_ai.output.messages", "") for s in agent)
    chats = by_name(spans, "chat ")
    assert any(f"{MARKER}-SYSTEM" in s["_attrs"].get("gen_ai.input.messages", "") for s in chats)
    assert any(f"{MARKER}-TOOLARG" in s["_attrs"].get("gen_ai.output.messages", "") for s in chats)
    tools = by_name(spans, "execute_tool")
    assert any(f"{MARKER}-TOOLARG" in s["_attrs"].get("gen_ai.tool.call.arguments", "") for s in tools)
    assert any(f"{MARKER}-TOOLARG" in s["_attrs"].get("gen_ai.tool.call.result", "") for s in tools)
    assert any("gen_ai.tool.definitions" in s["_attrs"] for s in chats)

    # the text of an error comes with the opt-in
    failed = [s for s in spans if s["status"]["code"] == "STATUS_CODE_ERROR"]
    assert any("does not exist" in s["status"].get("message", "") for s in failed)

    # a stack trace and the machine's identity never do
    everything = collector.everything()
    assert "exception.stacktrace" not in everything and "Traceback" not in everything
    for label, value in machine_identifiers.items():
        assert value not in everything, f"{label} left the process even with content on"


# ---------------------------------------------------------------------------
# In-process: classify every attribute the installed AgentScope emits.
# ---------------------------------------------------------------------------


class _Recorder(SpanExporter):
    def __init__(self):
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


@pytest.fixture(scope="module")
def raw_spans():
    """Real AgentScope spans, as the SDK hands them to an exporter, from all four scenarios."""
    import app
    from fake_openai import FakeOpenAI

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    trace.set_tracer_provider(provider)
    server = FakeOpenAI(api_key=MODEL_KEY, tool_arg=f"{MARKER}-TOOLARG")
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", MODEL_KEY)
    patch.setenv("OPENAI_BASE_URL", server.url)
    patch.setenv("OPENAI_MODEL", "fake-model")
    try:
        for scenario in ("chat", "nostream", "tool-error", "model-error"):
            try:
                asyncio.run(app.run(scenario, PROMPT, SYSTEM))
            except Exception:
                assert scenario == "model-error"
        provider.force_flush()
        return list(memory.get_finished_spans())
    finally:
        patch.undo()
        server.close()


def test_every_attribute_is_classified(raw_spans):
    emitted = {key for span in raw_spans for key in span.attributes}
    unclassified = emitted - METADATA_ATTRIBUTES - CONTENT_ATTRIBUTES
    assert not unclassified, f"AgentScope now emits attributes this recipe has not reviewed: {sorted(unclassified)}"
    assert emitted & CONTENT_ATTRIBUTES and emitted & METADATA_ATTRIBUTES


def test_content_mode_preserves_every_native_key(raw_spans):
    recorder = _Recorder()
    ContentFilterExporter(recorder, capture_content=True).export(raw_spans)
    assert len(recorder.spans) == len(raw_spans)
    for raw, exported in zip(raw_spans, recorder.spans):
        assert dict(exported.attributes) == dict(raw.attributes), "content mode must not drop or change an attribute"
        assert exported.name == raw.name and exported.get_span_context() == raw.get_span_context()
        assert exported.parent == raw.parent and exported.status.status_code == raw.status.status_code
        for event in exported.events:
            assert "exception.stacktrace" not in event.attributes


def test_metadata_mode_drops_only_what_is_not_metadata(raw_spans):
    recorder = _Recorder()
    ContentFilterExporter(recorder, capture_content=False).export(raw_spans)
    for raw, exported in zip(raw_spans, recorder.spans):
        assert set(exported.attributes) == set(raw.attributes) & METADATA_ATTRIBUTES
        assert all(exported.attributes[k] == raw.attributes[k] for k in exported.attributes)
        assert MARKER not in json.dumps(dict(exported.attributes))
        if exported.status.description:
            assert MARKER not in exported.status.description and "\n" not in exported.status.description
