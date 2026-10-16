"""Drop error details from spans before they leave the process.

The OpenAI instrumentor records a failed call as an ERROR span with
  * a status message that holds the SDK's error text (for Helicone this includes the
    response body the gateway or the provider returned),
  * an `exception` event with `exception.message` (the same text) and
    `exception.stacktrace` (file paths from the machine, including the user name).
FI_HIDE_INPUTS / FI_HIDE_OUTPUTS do not cover these. Wrap the exporter with this
class to keep the ERROR status and the exception class, and drop the rest.
"""
from __future__ import annotations

from typing import Sequence

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode

_DROP = {"exception.message", "exception.stacktrace"}


def _scrub(span: ReadableSpan) -> ReadableSpan:
    events = []
    for event in span.events:
        if event.name == "exception":
            attrs = {k: v for k, v in (event.attributes or {}).items() if k not in _DROP}
            events.append(Event(event.name, attrs, event.timestamp))
        else:
            events.append(event)
    status = span.status
    if status.status_code == StatusCode.ERROR:
        status = Status(StatusCode.ERROR)  # keep ERROR, drop the description
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


class RedactErrorDetailsExporter(SpanExporter):
    def __init__(self, inner: SpanExporter):
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_scrub(s) for s in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)
