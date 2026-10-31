"""The released TraceConfig replaces the copied exporter filter (no network)."""

from __future__ import annotations

import pytest

from fi_instrumentation import FITracer, TraceConfig
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode


@pytest.mark.parametrize("hide_content", [False, True])
def test_maintained_config_hides_error_details_and_preserves_metadata(hide_content):
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource({"project_name": "p"}))
    provider.add_span_processor(SimpleSpanProcessor(memory))
    tracer = FITracer(
        provider.get_tracer("test"),
        config=TraceConfig(
            hide_inputs=hide_content,
            hide_outputs=hide_content,
            hide_error_details=True,
        ),
    )
    try:
        with tracer.start_as_current_span("ok", attributes={"input.value": "hello"}):
            pass
        with tracer.start_as_current_span("failed") as span:
            try:
                raise RuntimeError("private error message /private/tools.py")
            except RuntimeError as error:
                span.record_exception(error)
            span.set_attribute("exception.message", "private error message")
            span.set_attribute("exception.stacktrace", "private traceback")
            span.set_status(Status(StatusCode.ERROR, "private error description"))
        assert provider.force_flush()
    finally:
        provider.shutdown()
    spans = {span.name: span for span in memory.get_finished_spans()}
    failed = spans["failed"]
    assert failed.status.status_code == StatusCode.ERROR
    assert failed.status.description is None
    (event,) = failed.events
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "RuntimeError"
    assert "exception.message" not in event.attributes
    assert "exception.stacktrace" not in event.attributes
    assert "exception.message" not in failed.attributes
    assert "exception.stacktrace" not in failed.attributes
    assert spans["ok"].attributes["input.value"] == ("__REDACTED__" if hide_content else "hello")
    assert failed.context.trace_id and failed.resource.attributes["project_name"] == "p"


def test_explicit_error_privacy_overrides_environment(monkeypatch):
    monkeypatch.setenv("FI_HIDE_ERROR_DETAILS", "false")
    assert TraceConfig(hide_error_details=True).hide_error_details
