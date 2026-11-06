"""Unit tests for the mapping, with no network and no Graphite run."""

from __future__ import annotations

from futureagi_grafi import GrafiExporter, map_attributes
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

GRAPHITE = {
    "id": "c1",
    "name": "WeatherTool",
    "type": "FunctionCallTool",
    "oi_span_type": "TOOL",
    "conversation_id": "conv-1",
    "invoke_id": "i1",
    "assistant_request_id": "r1",
    "user_id": "",
    "kwargs": {"note": "secret"},
    "input": '[{"content": "hello"}]',
    "output": '[{"content": "hi"}]',
}


def test_renames():
    mapped = map_attributes(GRAPHITE, capture_content=True)
    assert mapped["fi.span.kind"] == "TOOL"
    assert mapped["input.value"] == GRAPHITE["input"]
    assert mapped["output.value"] == GRAPHITE["output"]
    assert mapped["session.id"] == "conv-1"
    assert not {"oi_span_type", "input", "output", "conversation_id", "user_id", "kwargs"} & set(mapped)


def test_empty_ids_and_dicts_are_dropped():
    mapped = map_attributes(GRAPHITE, capture_content=True)
    assert "user.id" not in mapped
    assert "kwargs" not in mapped
    assert map_attributes({"user_id": "u-9", "conversation_id": ""}, True) == {"user.id": "u-9"}


def test_without_content_only_metadata_remains():
    mapped = map_attributes(GRAPHITE, capture_content=False)
    assert set(mapped) == {"id", "name", "type", "fi.span.kind", "session.id", "invoke_id", "assistant_request_id"}


def test_unknown_attributes_are_content():
    attributes = {"brand_new": "x", "oi_span_type": "LLM"}
    assert map_attributes(attributes, False) == {"fi.span.kind": "LLM"}
    assert map_attributes(attributes, True) == {"fi.span.kind": "LLM", "brand_new": "x"}


def test_stack_traces_and_error_dumps_never_leave():
    attributes = {"error": "boom /Users/x", "error.stack": "Traceback ...", "error.details": "{}", "error.type": "E", "error.message": "m"}
    assert map_attributes(attributes, True) == {"error.type": "E", "error.message": "m"}
    assert map_attributes(attributes, False) == {"error.type": "E"}


def test_token_counts_of_a_provider_span_are_metadata():
    attributes = {"llm.token_count.total": 38, "llm.model_name": "m", "llm.input_messages.0.message.content": "secret"}
    assert map_attributes(attributes, False) == {"llm.token_count.total": 38, "llm.model_name": "m"}


def _export(capture_content, configure):
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"project_name": "unit"}))
    provider.add_span_processor(SimpleSpanProcessor(GrafiExporter(memory, capture_content)))
    with provider.get_tracer("grafi").start_as_current_span("x.invoke") as span:
        configure(span)
    return memory.get_finished_spans()[0]


def test_exporter_sets_the_mapped_attributes_and_keeps_the_rest_of_the_span():
    def configure(span):
        span.set_attributes({"oi_span_type": "AGENT", "input": "secret", "conversation_id": "c"})

    span = _export(False, configure)
    assert span.name == "x.invoke"
    assert dict(span.attributes) == {"fi.span.kind": "AGENT", "session.id": "c"}
    assert span.resource.attributes["project_name"] == "unit"
    assert span.context.trace_id and span.context.span_id


def test_exporter_hides_exception_text_and_stack_without_content():
    def configure(span):
        try:
            raise ValueError("raw text with /Users/someone/secret.py")
        except ValueError as error:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, f"ValueError: {error}"))

    span = _export(False, configure)
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == "ValueError"
    assert [dict(e.attributes) for e in span.events] == [{"exception.type": "ValueError"}]


def test_exporter_keeps_the_message_but_not_the_stack_with_content():
    def configure(span):
        try:
            raise ValueError("raw text")
        except ValueError as error:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, f"ValueError: {error}"))

    span = _export(True, configure)
    assert span.status.description == "ValueError: raw text"
    assert dict(span.events[0].attributes) == {"exception.type": "ValueError", "exception.message": "raw text"}
