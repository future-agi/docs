"""Tracer provider for a Temporal application that sends traces to Future AGI.

Imported by the worker and the starter. Never import it from workflow code: a workflow must
not build or own an exporter (it is re-run on replay, and the workflow sandbox forbids sockets).

    provider = setup_tracing()          # once per process, before Client.connect()
    ...
    provider.force_flush()              # short-lived processes: before exit
    provider.shutdown()

Environment:
    FI_API_KEY, FI_SECRET_KEY   Future AGI keys (sent as X-Api-Key and X-Secret-Key)
    FI_BASE_URL                 https://api.futureagi.com, or your self-hosted Future AGI
    FI_PROJECT_NAME             Observe project (resource attribute project_name)
    KEEP_TEMPORAL_ERROR_TEXT    "true" keeps exception messages and the text of ERROR statuses
                                (default: removed; stack traces are never exported, see SafeSpanExporter)
"""
import os
from collections.abc import Sequence
from typing import Optional

from fi_instrumentation.otel import BatchSpanProcessor
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode
from temporalio.contrib.opentelemetry import ReplaySafeTracerProvider, create_tracer_provider

SESSION_ID = "session.id"  # Future AGI groups spans with the same value into one session
WORKFLOW_ID = "temporalWorkflowID"  # set by OpenTelemetryPlugin on its workflow and activity spans


class WorkflowIdAsSession(SpanProcessor):
    """Use the Temporal workflow id as the Future AGI session id, unless the app already set one.

    Spans made by OpenTelemetryPlugin carry the workflow id, so they get it directly. Every other
    span (the model call, your own spans) takes its parent's session id when it starts.
    """

    def on_start(self, span: Span, parent_context: Optional[Context] = None) -> None:
        attributes = span.attributes or {}
        if SESSION_ID in attributes:
            return
        if WORKFLOW_ID in attributes:
            span.set_attribute(SESSION_ID, attributes[WORKFLOW_ID])
            return
        parent_attributes = getattr(trace.get_current_span(parent_context), "attributes", None) or {}
        if SESSION_ID in parent_attributes:
            span.set_attribute(SESSION_ID, parent_attributes[SESSION_ID])


class SafeSpanExporter(SpanExporter):
    """Remove exception text from spans before they leave the process.

    OpenTelemetryPlugin puts "<ExceptionType>: <message>" in the status of a failed workflow or
    activity span, and every span records an `exception` event whose message can quote user data
    and whose stack trace holds local file paths and user names. This keeps the ERROR status and
    the exception type and drops the rest. With keep_error_text=True (or KEEP_TEMPORAL_ERROR_TEXT=true)
    the status text and the exception message are exported; stack traces are never exported.
    """

    def __init__(self, exporter: SpanExporter, keep_error_text: bool = False) -> None:
        self._exporter = exporter
        self._keep_error_text = keep_error_text

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._exporter.export([self._scrub(span) for span in spans])

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)

    def _scrub(self, span: ReadableSpan) -> ReadableSpan:
        status = span.status
        dropped = {"exception.stacktrace"} if self._keep_error_text else {"exception.message", "exception.stacktrace"}
        if status.status_code == StatusCode.ERROR and status.description and not self._keep_error_text:
            status = Status(StatusCode.ERROR, "error")
        events = [
            Event(
                event.name,
                {k: v for k, v in (event.attributes or {}).items() if k not in dropped}
                if event.name == "exception"
                else event.attributes,
                event.timestamp,
            )
            for event in span.events
        ]
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=span.resource,
            attributes=span.attributes,
            events=events,
            links=span.links,
            kind=span.kind,
            status=status,
            start_time=span.start_time,
            end_time=span.end_time,
            instrumentation_scope=span.instrumentation_scope,
        )


def setup_tracing(
    instrument_openai: bool = True, exporter: Optional[SpanExporter] = None
) -> ReplaySafeTracerProvider:
    """Build the replay-safe provider, register it globally, and trace OpenAI calls through it.

    `exporter` replaces the Future AGI exporter (the tests pass an in-memory one).
    """
    if exporter is None:
        base_url = os.environ.get("FI_BASE_URL", "https://api.futureagi.com").rstrip("/")
        exporter = OTLPSpanExporter(
            endpoint=f"{base_url}/tracer/v1/traces",
            headers={"X-Api-Key": os.environ["FI_API_KEY"], "X-Secret-Key": os.environ["FI_SECRET_KEY"]},
            compression=Compression.NoCompression,  # the Future AGI HTTP receiver rejects gzip bodies
        )
    provider = create_tracer_provider(
        resource=Resource.create(
            {"project_name": os.environ.get("FI_PROJECT_NAME", "temporal-agent"), "project_type": "observe"}
        )
    )
    provider.add_span_processor(WorkflowIdAsSession())
    provider.add_span_processor(
        BatchSpanProcessor(
            span_exporter=SafeSpanExporter(
                exporter, keep_error_text=os.environ.get("KEEP_TEMPORAL_ERROR_TEXT", "").lower() == "true"
            )
        )
    )
    # OpenTelemetryPlugin reads the global provider, and refuses one that is not replay-safe.
    trace.set_tracer_provider(provider)
    if instrument_openai:
        from traceai_openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument(tracer_provider=provider)
    return provider
