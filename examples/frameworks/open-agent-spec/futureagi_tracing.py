"""Send Open Agent Spec (pyagentspec) runs on the LangGraph adapter to Future AGI.

pyagentspec has no OpenTelemetry exporter. Its tracing package (``pyagentspec.tracing``)
is a span bus: a ``Trace`` hands Agent Spec spans and events to ``SpanProcessor`` objects,
and nothing in pyagentspec 26.3.1 imports OpenTelemetry. Registering a tracer provider
alone exports nothing.

The LangGraph adapter (``pyagentspec.adapters.langgraph.AgentSpecLoader``) compiles an
Agent Spec ``Agent`` into a LangGraph graph and runs it with LangChain chat models and
tools. traceAI's LangChain instrumentor traces that run: one trace per agent run, the
agent graph (named after the Agent Spec agent) as the root, a span per model call with
model and token counts, and a span per tool call.

``setup_tracing()`` does three things:

* ``register()`` builds the Future AGI tracer provider: resource ``project_name`` and
  ``project_type=observe``, OTLP/HTTP to ``$FI_BASE_URL/tracer/v1/traces`` (no compression), and
  the ``X-Api-Key`` / ``X-Secret-Key`` headers from ``FI_API_KEY`` / ``FI_SECRET_KEY``;
* the exporter is wrapped in ``ErrorDetailFilter``. LangChain writes the whole Python
  traceback, with local file paths, into the status of a failed span, and OpenTelemetry
  adds an ``exception.stacktrace`` event attribute. Neither is ever exported. With content
  hidden, the error message is also reduced to the exception class name;
* ``LangChainInstrumentor`` is instrumented on that provider.

Content follows traceAI's default: prompts, model outputs, tool arguments and tool
results are captured. Set ``FI_HIDE_INPUTS=true`` and ``FI_HIDE_OUTPUTS=true`` (or pass
``TraceConfig(hide_inputs=True, hide_outputs=True)``) to turn that off.

Call ``setup_tracing()`` once, before the first agent run.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from fi_instrumentation import TraceConfig, register
from fi_instrumentation.fi_types import ProjectType
from fi_instrumentation.otel import HTTPSpanExporter, TracerProvider
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode
from traceai_langchain import LangChainInstrumentor

__all__ = ["ErrorDetailFilter", "setup_tracing", "strip_error_detail"]

_TRACEBACK = "Traceback (most recent call last)"
_EXCEPTION_CLASS = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*[(:]")


def _exception_type(description: str, events: Sequence[Event]) -> Optional[str]:
    for event in events:
        if event.name == "exception" and event.attributes:
            value = event.attributes.get("exception.type")
            if value:
                return str(value)
    match = _EXCEPTION_CLASS.match(description or "")
    return match.group(1) if match else None


def strip_error_detail(description: Optional[str], hide_error_text: bool,
                       events: Sequence[Event] = ()) -> Optional[str]:
    """Return a span status description that is safe to export.

    LangChain sets ``repr(error)`` followed by the full traceback. The traceback is
    always removed. With ``hide_error_text`` only the exception class name is kept.
    """
    if not description:
        return description
    if hide_error_text:
        return _exception_type(description, events) or "error"
    head = description.split(_TRACEBACK, 1)[0].strip()
    return head or (_exception_type(description, events) or "error")


def _filter_event(event: Event, hide_error_text: bool) -> Event:
    if event.name != "exception":
        return event
    drop = {"exception.stacktrace"}
    if hide_error_text:
        drop.add("exception.message")
    attributes = {k: v for k, v in (event.attributes or {}).items() if k not in drop}
    return Event(name=event.name, attributes=attributes, timestamp=event.timestamp)


def _filter_span(span: ReadableSpan, hide_error_text: bool) -> ReadableSpan:
    events = tuple(_filter_event(e, hide_error_text) for e in span.events)
    status = span.status
    if status.status_code == StatusCode.ERROR:
        status = Status(StatusCode.ERROR,
                        strip_error_detail(status.description, hide_error_text, span.events))
    attributes = dict(span.attributes or {})
    attributes.pop("exception.stacktrace", None)
    if hide_error_text:
        attributes.pop("exception.message", None)
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=events,
        links=span.links,
        kind=span.kind,
        status=status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class ErrorDetailFilter(SpanExporter):
    """Wrap a span exporter so that error details leave the process only as far as allowed.

    * a stack trace is never exported (span status, ``exception`` events, attributes);
    * with ``hide_error_text`` the error message is replaced by the exception class name.
    """

    def __init__(self, exporter: SpanExporter, hide_error_text: bool) -> None:
        self._exporter = exporter
        self._hide_error_text = hide_error_text

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._exporter.export([_filter_span(s, self._hide_error_text) for s in spans])

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)


def setup_tracing(project_name: Optional[str] = None,
                  config: Optional[TraceConfig] = None) -> TracerProvider:
    """Register the Future AGI tracer provider and instrument LangChain/LangGraph.

    ``project_name`` defaults to ``$FI_PROJECT_NAME``. ``config`` defaults to
    ``TraceConfig()``, which reads the ``FI_HIDE_*`` environment variables.
    """
    config = config or TraceConfig()
    hide_error_text = bool(config.hide_inputs or config.hide_outputs)
    tracer_provider = register(
        project_name=project_name,
        project_type=ProjectType.OBSERVE,
        span_exporter=ErrorDetailFilter(HTTPSpanExporter(), hide_error_text),
        verbose=False,
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider, config=config)
    return tracer_provider
