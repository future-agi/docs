"""Send AgentScope 2.x traces to Future AGI.

AgentScope 2.x does not take an endpoint, headers or a resource. Its
``TracingMiddleware`` creates spans on the global OpenTelemetry tracer and nothing else,
so the application owns the tracer provider. ``setup_tracing`` builds that provider:

* the resource carries ``project_name`` (Future AGI files spans by it) and ``project_type``;
* the OTLP/HTTP exporter carries ``X-Api-Key`` and ``X-Secret-Key``, sends no gzip, and
  posts to ``<FI_BASE_URL>/tracer/v1/traces`` (traces only, no logs or metrics);
* by default only metadata leaves the process (see ``METADATA_ATTRIBUTES``). Set
  ``FI_CAPTURE_CONTENT=1`` (or ``capture_content=True``) to also export prompts, answers,
  tool arguments and tool results, and the text of an error;
* a stack trace is never exported, in either mode: it holds local file paths.

AgentScope itself has no switch for content: ``TracingMiddleware`` always writes the
messages and tool payloads onto the spans. ``ContentFilterExporter`` is the off switch.

Call ``setup_tracing`` once, before the first agent reply.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    Compression,
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Status, StatusCode

# Attributes of AgentScope's own spans that describe a call without containing what was
# said or done. Anything not listed here is dropped unless content capture is on, so an
# attribute added by a later AgentScope release stays private until it is reviewed.
METADATA_ATTRIBUTES = frozenset(
    {
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.request.temperature",
        "gen_ai.request.top_p",
        "gen_ai.request.top_k",
        "gen_ai.request.max_tokens",
        "gen_ai.request.presence_penalty",
        "gen_ai.request.frequency_penalty",
        "gen_ai.request.seed",
        "gen_ai.response.id",
        "gen_ai.response.finish_reasons",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "agentscope.usage.cache_input_tokens",
        "agentscope.usage.cache_creation_input_tokens",
        "gen_ai.agent.name",
        "gen_ai.conversation.id",
        "gen_ai.tool.name",
        "gen_ai.tool.call.id",
        "agentscope.agent.reply_id",
        "agentscope.agent.hitl_pending_tools",
        "agentscope.agent.external_execution_pending_tools",
        "agentscope.agent.incoming_event_type",
        "agentscope.agent.is_external_execution",
    }
)

_TRUE = {"1", "true", "yes", "on"}


def _filter_event(event: Event, capture_content: bool) -> Event:
    """Keep an event's name and time. The stack trace of an exception event is always
    dropped (it holds local file paths); its message, which can hold user text, is kept
    only with content on."""
    attributes = dict(event.attributes or {})
    if event.name == "exception":
        keep = {"exception.type", "exception.message"} if capture_content else {"exception.type"}
        attributes = {key: value for key, value in attributes.items() if key in keep}
    elif not capture_content:
        attributes = {}
    return Event(name=event.name, attributes=attributes, timestamp=event.timestamp)


class _FilteredSpan:
    """A read-only view of a finished span, with the content removed.

    Everything the OTLP encoder reads is delegated to the real span, except the
    attributes, the events and the status.
    """

    def __init__(self, span: ReadableSpan, capture_content: bool) -> None:
        self._span = span
        self._attributes = {
            key: value
            for key, value in (span.attributes or {}).items()
            if capture_content or key in METADATA_ATTRIBUTES
        }
        self._events = tuple(_filter_event(event, capture_content) for event in span.events)
        status = span.status
        description = status.description
        if status.status_code == StatusCode.ERROR and not capture_content:
            # The status message is str(exception). Keep the class name instead.
            description = next(
                (
                    event.attributes["exception.type"]
                    for event in self._events
                    if "exception.type" in event.attributes
                ),
                None,
            )
        self._status = Status(status.status_code, description)

    def __getattr__(self, name: str):
        return getattr(self._span, name)

    @property
    def attributes(self) -> Mapping[str, object]:
        return self._attributes

    @property
    def events(self) -> Sequence[Event]:
        return self._events

    @property
    def status(self) -> Status:
        return self._status


class ContentFilterExporter(SpanExporter):
    """Wrap an exporter so that content, and always stack traces, never leave the process."""

    def __init__(self, inner: SpanExporter, capture_content: bool = False) -> None:
        self._inner = inner
        self._capture_content = capture_content

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_FilteredSpan(span, self._capture_content) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def setup_tracing(
    project_name: str | None = None,
    *,
    capture_content: bool | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    secret_key: str | None = None,
) -> TracerProvider:
    """Install a tracer provider that exports AgentScope's spans to Future AGI."""
    project_name = project_name or os.environ.get("FI_PROJECT_NAME") or "agentscope-app"
    if capture_content is None:
        capture_content = os.environ.get("FI_CAPTURE_CONTENT", "").lower() in _TRUE
    base_url = (base_url or os.environ.get("FI_BASE_URL") or "https://api.futureagi.com").rstrip("/")
    api_key = api_key or os.environ["FI_API_KEY"]
    secret_key = secret_key or os.environ["FI_SECRET_KEY"]

    exporter = OTLPSpanExporter(
        endpoint=f"{base_url}/tracer/v1/traces",
        headers={"X-Api-Key": api_key, "X-Secret-Key": secret_key},
        compression=Compression.NoCompression,  # the Future AGI collector refuses gzip
    )

    provider = TracerProvider(
        resource=Resource.create({"project_name": project_name, "project_type": "observe"})
    )
    provider.add_span_processor(BatchSpanProcessor(ContentFilterExporter(exporter, capture_content)))
    trace.set_tracer_provider(provider)
    return provider
