"""Privacy: with content capture off (the default) no prompt, answer, tool argument, tool
result, error text or stack trace leaves the process, and nothing identifies the machine.

Every test searches every byte the recording collector received (request bodies, decoded
spans, headers), not just the attributes the recipe is expected to set.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from conftest import MODEL_KEY, FI_API_KEY, FI_SECRET_KEY, ROOT, MARKER, Collector, FakeOpenAI, by_name

PROMPT = f"{MARKER}-prompt"
SYSTEM = f"{MARKER}-system"
TOOL_ARG = f"{MARKER}-arg"
NOTE = f"{MARKER}-kwargs"
EMAIL = "someone.private@example.com"

ENV = {"APP_PROMPT": f"Weather for {PROMPT}, mail me at {EMAIL}", "APP_SYSTEM": f"{SYSTEM} Use the tool.", "APP_KWARGS": NOTE}


@pytest.fixture()
def marked_model():
    server = FakeOpenAI(api_key=MODEL_KEY, tool_arg=TOOL_ARG)
    yield server
    server.close()


@pytest.fixture()
def run_marked(run_app, marked_model):
    def _run(scenario, env=None, **kwargs):
        return run_app(scenario, env={**ENV, "OPENAI_BASE_URL": marked_model.url, **(env or {})}, **kwargs)

    return _run


CONTENT = {"prompt": PROMPT, "system prompt": SYSTEM, "tool argument, result and answer": TOOL_ARG, "kwargs": NOTE, "email": EMAIL}


@pytest.mark.parametrize("scenario", ["chat", "tool-error", "model-error"])
def test_nothing_private_leaves_by_default(run_marked, collector, machine_identifiers, scenario):
    done = run_marked(scenario)
    assert done.returncode == 0, done.stdout + done.stderr
    assert collector.spans()
    seen = collector.everything()
    for what, needle in {**CONTENT, **machine_identifiers}.items():
        assert needle not in seen, f"{what} reached the collector"
    for needle in (MODEL_KEY, "Traceback", "site-packages", ".py\", line"):
        assert needle not in seen
    # The Future AGI keys are headers only, never span data.
    for span in collector.spans():
        text = str(span)
        assert FI_API_KEY not in text and FI_SECRET_KEY not in text


def test_the_provider_instrumentor_spans_are_filtered_too(run_marked, collector, machine_identifiers):
    """The OpenInference OpenAI instrumentor writes the full prompt and answer onto its own spans.
    It runs on the same provider, so the same exporter filters it."""
    done = run_marked("chat", env={"GRAFI_PROVIDER_SPANS": "1"})
    assert done.returncode == 0, done.stdout + done.stderr
    provider_spans = [s for s in collector.spans() if s["_attrs"].get("openinference.span.kind") == "LLM"]
    assert provider_spans
    seen = collector.everything()
    for what, needle in {**CONTENT, **machine_identifiers}.items():
        assert needle not in seen, f"{what} reached the collector"
    assert {"llm.model_name", "llm.token_count.total"} <= {k for s in provider_spans for k in s["_attrs"]}
    assert not any(k.startswith(("llm.input_messages", "llm.output_messages", "llm.tools", "input.", "output.")) for s in provider_spans for k in s["_attrs"])


def test_the_error_is_still_visible_as_a_class_name(run_marked, collector):
    run_marked("tool-error")
    spans = collector.spans()
    tool = by_name(spans, "WeatherTool.invoke")[0]
    assert tool["status"]["code"] == "STATUS_CODE_ERROR"
    assert tool["status"]["message"].endswith("FunctionCallException")
    assert tool["_attrs"]["error.type"] == "FunctionCallException"
    event = tool["events"][0]
    assert event["name"] == "exception"
    keys = {a["key"] for a in event["attributes"]}
    assert keys == {"exception.type"}, "no exception message, no stack trace"


def test_only_metadata_attributes_are_exported_by_default(run_marked, collector):
    from futureagi_grafi import METADATA_ATTRIBUTES

    run_marked("chat")
    exported = {k for s in collector.spans() for k in s["_attrs"]}
    assert exported <= METADATA_ATTRIBUTES
    assert {"fi.span.kind", "session.id", "name", "type"} <= exported
    assert not exported & {"input.value", "output.value", "input", "output"}


def test_the_opt_in_exports_content_and_still_no_stack_trace_or_machine_identifiers(run_marked, collector, machine_identifiers):
    done = run_marked("chat", env={"FI_CAPTURE_CONTENT": "1"})
    assert done.returncode == 0, done.stdout + done.stderr
    seen = collector.everything()
    for what in ("prompt", "tool argument, result and answer"):
        assert CONTENT[what] in seen, f"opt-in should export the {what}"
    # Graphite keeps the system prompt on the LLM tool, not in the messages it records on its spans.
    assert SYSTEM not in seen
    assert NOTE in seen  # inside the serialized input, not as a dict attribute
    assert all("kwargs" not in s["_attrs"] for s in collector.spans())
    for what, needle in machine_identifiers.items():
        assert needle not in seen, f"{what} reached the collector"
    assert MODEL_KEY not in seen
    spans = collector.spans()
    assert by_name(spans, "WeatherAssistant.run")[0]["_attrs"]["input.value"]
    assert TOOL_ARG in by_name(spans, "WeatherTool.invoke")[0]["_attrs"]["input.value"]


def test_the_opt_in_exports_error_text_but_never_the_stack_trace(run_marked, collector, machine_identifiers):
    run_marked("tool-error", env={"FI_CAPTURE_CONTENT": "1"})
    seen = collector.everything()
    assert f"weather backend refused the request for {TOOL_ARG}" in seen
    for needle in ("Traceback", "site-packages", ".py\", line", *machine_identifiers.values()):
        assert needle not in seen
    tool = by_name(collector.spans(), "WeatherTool.invoke")[0]
    assert "error.stack" not in tool["_attrs"] and "error.details" not in tool["_attrs"] and "error" not in tool["_attrs"]
    assert {a["key"] for a in tool["events"][0]["attributes"]} <= {"exception.type", "exception.message"}


def test_graphites_own_switch_still_removes_payloads_when_the_recipe_opts_in(run_marked, collector):
    """GRAFI_SPAN_DISABLE_PAYLOADS stops Graphite writing input and output onto spans at all, so
    even FI_CAPTURE_CONTENT=1 has nothing to export."""
    done = run_marked("chat", env={"FI_CAPTURE_CONTENT": "1", "GRAFI_SPAN_DISABLE_PAYLOADS": "1"})
    assert done.returncode == 0, done.stdout + done.stderr
    spans = collector.spans()
    assert spans
    assert not any("input.value" in s["_attrs"] or "output.value" in s["_attrs"] for s in spans)
    assert PROMPT not in collector.everything()


def test_the_documented_switch_values(run_marked, collector):
    for value, expected in (("0", False), ("", False), ("true", True), ("yes", True)):
        before = len(collector.spans())
        run_marked("chat", env={"FI_CAPTURE_CONTENT": value})
        new = collector.spans()[before:]
        assert any("input.value" in s["_attrs"] for s in new) is expected, value


def test_every_attribute_graphite_sets_is_classified(model):
    """Drift guard. Graphite 0.0.36 sets a fixed set of span attributes. If a later release adds
    one, this fails until someone decides whether it is metadata (add it to METADATA_ATTRIBUTES)
    or content (leave it out: it is then dropped unless content capture is on)."""
    from futureagi_grafi import METADATA_ATTRIBUTES, NEVER_EXPORTED, RENAMES
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    import os
    import app

    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"project_name": "drift"}))
    provider.add_span_processor(SimpleSpanProcessor(memory))
    os.environ.update({"OPENAI_API_KEY": MODEL_KEY, "OPENAI_BASE_URL": model.url, "OPENAI_MODEL": "fake-model"})
    for scenario in ("chat", "tool-error", "model-error"):
        _run_in_process(provider, scenario)
    raw = {key for span in memory.get_finished_spans() for key in span.attributes}
    assert raw, "no spans recorded"
    known = set(RENAMES) | NEVER_EXPORTED | METADATA_ATTRIBUTES | {"kwargs", "error.message"}
    unclassified = raw - known
    assert not unclassified, f"new Graphite span attributes need a decision: {sorted(unclassified)}"
    # every attribute that is neither renamed nor metadata is content, and is not exported by default
    content = raw - set(RENAMES) - METADATA_ATTRIBUTES
    assert {"input", "output", "kwargs", "error", "error.message", "error.stack", "error.details"} >= content


def _run_in_process(provider, scenario):
    import os
    import app
    from grafi.common.events.topic_events.publish_to_topic_event import PublishToTopicEvent
    from grafi.common.models.invoke_context import InvokeContext
    from grafi.common.models.message import Message
    from grafi.runtime import ExecutionServices, GrafiRuntime

    runtime = GrafiRuntime(ExecutionServices(tracer=provider.get_tracer("grafi")))
    context = InvokeContext(
        conversation_id="drift", invoke_id=uuid.uuid4().hex, assistant_request_id=uuid.uuid4().hex, user_id="u", kwargs={"a": 1}
    )
    request = PublishToTopicEvent(invoke_context=context, data=[Message(role="user", content="weather?")])

    async def go():
        try:
            return [e async for e in runtime.invoke(app.build(scenario), request)]
        except Exception:  # noqa: BLE001
            return []

    asyncio.run(go())
