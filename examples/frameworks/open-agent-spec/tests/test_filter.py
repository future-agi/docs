"""Unit tests for ErrorDetailFilter / strip_error_detail on SDK spans (no network)."""

from __future__ import annotations

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from futureagi_tracing import ErrorDetailFilter, strip_error_detail

LANGCHAIN_ERROR = (
    "RuntimeError('weather service unavailable for Lisbon')Traceback (most recent call last):\n"
    '\n  File "/Users/someone/app/tools.py", line 3, in get_weather\n    raise RuntimeError(...)\n'
)


def make_spans(hide_error_text: bool):
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource({"project_name": "p"}))
    provider.add_span_processor(SimpleSpanProcessor(ErrorDetailFilter(memory, hide_error_text)))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("ok", attributes={"input.value": "hello"}):
        pass
    with tracer.start_as_current_span("failed") as span:
        try:
            raise RuntimeError("weather service unavailable for Lisbon")
        except RuntimeError as error:
            span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, LANGCHAIN_ERROR))
    provider.shutdown()
    return {s.name: s for s in memory.get_finished_spans()}


def test_strip_keeps_message_without_traceback():
    assert strip_error_detail(LANGCHAIN_ERROR, False) == "RuntimeError('weather service unavailable for Lisbon')"


def test_strip_hidden_keeps_only_the_class_name():
    assert strip_error_detail(LANGCHAIN_ERROR, True) == "RuntimeError"
    assert strip_error_detail("openai.AuthenticationError: 401", True) == "openai.AuthenticationError"
    assert strip_error_detail("no class here", True) == "error"
    assert strip_error_detail(None, True) is None
    assert strip_error_detail("", False) == ""


def test_filter_default_drops_stack_trace_only():
    spans = make_spans(hide_error_text=False)
    failed = spans["failed"]
    assert failed.status.description == "RuntimeError('weather service unavailable for Lisbon')"
    (event,) = failed.events
    assert event.name == "exception"
    assert "exception.stacktrace" not in event.attributes
    assert event.attributes["exception.message"] == "weather service unavailable for Lisbon"
    assert event.attributes["exception.type"] == "RuntimeError"
    assert spans["ok"].attributes["input.value"] == "hello"
    assert failed.context.trace_id and failed.resource.attributes["project_name"] == "p"


def test_filter_hidden_drops_message_and_stack_trace():
    failed = make_spans(hide_error_text=True)["failed"]
    assert failed.status.description == "RuntimeError"
    (event,) = failed.events
    assert set(event.attributes) <= {"exception.type", "exception.escaped"}


def test_filter_forwards_flush_and_shutdown():
    calls = []

    class Inner(InMemorySpanExporter):
        def force_flush(self, timeout_millis=30000):
            calls.append(("flush", timeout_millis))
            return True

        def shutdown(self):
            calls.append(("shutdown", None))

    wrapper = ErrorDetailFilter(Inner(), False)
    assert wrapper.force_flush(5) is True
    wrapper.shutdown()
    assert calls == [("flush", 5), ("shutdown", None)]
