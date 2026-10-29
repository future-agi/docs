"""tracing.py without a Temporal server or a network: the exporter wrapper, the session processor, the wiring."""
import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import StatusCode
from temporalio.contrib.opentelemetry import ReplaySafeTracerProvider

import tracing
from conftest import FIXTURE_FI_API_KEY, FIXTURE_FI_SECRET_KEY
from helpers import RecordingExporter, dump

SECRET_TEXT = "alice@example.com asked about order 4711"


def provider_with(exporter, *processors, keep_error_text=False):
    provider = TracerProvider(resource=Resource.create({"project_name": "p"}))
    for processor in processors:
        provider.add_span_processor(processor)
    provider.add_span_processor(SimpleSpanProcessor(tracing.SafeSpanExporter(exporter, keep_error_text=keep_error_text)))
    return provider


def failing_span(provider):
    tracer = provider.get_tracer("t")
    try:
        with tracer.start_as_current_span("RunActivity:get_weather", attributes={"temporalWorkflowID": "wf-1"}) as span:
            span.set_status(trace.Status(StatusCode.ERROR, f"ValueError: {SECRET_TEXT}"))
            raise ValueError(SECRET_TEXT)
    except ValueError:
        pass


def test_error_text_and_stack_trace_are_removed_by_default():
    exporter = RecordingExporter()
    failing_span(provider_with(exporter))
    (span,) = exporter.spans
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == "error"
    (event,) = span.events
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "ValueError"
    assert "exception.message" not in event.attributes and "exception.stacktrace" not in event.attributes
    assert SECRET_TEXT not in dump(exporter.spans) and "Traceback" not in dump(exporter.spans)
    assert span.attributes["temporalWorkflowID"] == "wf-1"  # everything else is untouched


def test_opt_in_keeps_the_message_but_never_the_stack_trace():
    exporter = RecordingExporter()
    failing_span(provider_with(exporter, keep_error_text=True))
    (span,) = exporter.spans
    assert SECRET_TEXT in span.status.description
    assert span.events[0].attributes["exception.message"] == SECRET_TEXT
    assert "exception.stacktrace" not in span.events[0].attributes
    assert "Traceback" not in dump(exporter.spans)


def test_a_span_without_errors_is_exported_unchanged():
    exporter = RecordingExporter()
    provider = provider_with(exporter)
    with provider.get_tracer("t").start_as_current_span("llm", attributes={"a": 1}):
        with provider.get_tracer("t").start_as_current_span("child") as child:
            child.add_event("note", {"k": "v"})
    child_span, parent_span = exporter.spans
    assert child_span.parent.span_id == parent_span.context.span_id
    assert child_span.context.trace_id == parent_span.context.trace_id
    assert child_span.events[0].name == "note" and child_span.events[0].attributes["k"] == "v"
    assert parent_span.attributes["a"] == 1 and parent_span.status.status_code == StatusCode.UNSET
    assert parent_span.resource.attributes["project_name"] == "p"


def test_workflow_id_becomes_the_session_id_and_children_inherit_it():
    exporter = RecordingExporter()
    provider = provider_with(exporter, tracing.WorkflowIdAsSession())
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("RunWorkflow:W", attributes={"temporalWorkflowID": "wf-1"}):
        with tracer.start_as_current_span("RunActivity:a", attributes={"temporalWorkflowID": "wf-1"}):
            with tracer.start_as_current_span("ChatCompletion"):
                pass
    with tracer.start_as_current_span("unrelated"):
        pass
    sessions = {s.name: s.attributes.get("session.id") for s in exporter.spans}
    assert sessions == {"ChatCompletion": "wf-1", "RunActivity:a": "wf-1", "RunWorkflow:W": "wf-1", "unrelated": None}


def test_an_application_session_id_is_not_overwritten():
    exporter = RecordingExporter()
    provider = provider_with(exporter, tracing.WorkflowIdAsSession())
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("RunWorkflow:W", attributes={"temporalWorkflowID": "wf-1", "session.id": "chat-42"}):
        with tracer.start_as_current_span("ChatCompletion"):
            pass
    assert {s.attributes["session.id"] for s in exporter.spans} == {"chat-42"}


def test_setup_wires_the_provider_resource_exporter_and_headers(fresh_otel, monkeypatch):
    seen = {}

    class FakeExporter(RecordingExporter):
        def __init__(self, **kwargs):
            super().__init__()
            seen.update(kwargs)

    monkeypatch.setattr(tracing, "OTLPSpanExporter", FakeExporter)
    monkeypatch.setenv("FI_BASE_URL", "https://fi.example.test/")
    monkeypatch.setenv("FI_PROJECT_NAME", "my-chatbot")
    provider = tracing.setup_tracing(instrument_openai=False)
    assert isinstance(provider, ReplaySafeTracerProvider)
    assert trace.get_tracer_provider() is provider  # OpenTelemetryPlugin reads the global provider
    assert seen["endpoint"] == "https://fi.example.test/tracer/v1/traces"
    assert seen["headers"] == {"X-Api-Key": FIXTURE_FI_API_KEY, "X-Secret-Key": FIXTURE_FI_SECRET_KEY}
    assert seen["compression"].name == "NoCompression"
    with provider.get_tracer("t").start_as_current_span("s"):
        pass
    resource = provider._tracer_provider.resource.attributes
    assert resource["project_name"] == "my-chatbot" and resource["project_type"] == "observe"
    provider.shutdown()


def test_setup_reads_the_error_text_opt_in_from_the_environment(fresh_otel, monkeypatch):
    exporter = RecordingExporter()
    monkeypatch.setenv("KEEP_TEMPORAL_ERROR_TEXT", "true")
    provider = tracing.setup_tracing(instrument_openai=False, exporter=exporter)
    failing_span(provider)
    provider.force_flush()
    assert SECRET_TEXT in dump(exporter.spans)
    provider.shutdown()


def test_the_exporter_uses_a_plain_text_error_status_not_a_stack_trace_even_without_the_wrapper_opt_in(fresh_otel):
    exporter = RecordingExporter()
    provider = tracing.setup_tracing(instrument_openai=False, exporter=exporter)
    failing_span(provider)
    provider.force_flush()
    assert SECRET_TEXT not in dump(exporter.spans)
    provider.shutdown()


@pytest.mark.parametrize("missing", ["FI_API_KEY", "FI_SECRET_KEY"])
def test_both_key_headers_are_required(fresh_otel, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(KeyError):
        tracing.setup_tracing(instrument_openai=False)
