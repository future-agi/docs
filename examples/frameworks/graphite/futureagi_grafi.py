"""Send Graphite (PyPI ``grafi``) traces to Future AGI.

Graphite emits OpenTelemetry spans through the tracer you put in ``ExecutionServices``.
Its own ``setup_tracing()`` helper cannot be used for Future AGI (plaintext gRPC, no
headers, ``service.name`` instead of ``project_name``), so the application builds the
tracer provider itself. ``create_tracer_provider`` does that:

* the resource carries ``project_name`` (Future AGI files spans by it) and ``project_type``;
* the OTLP/HTTP exporter carries ``X-Api-Key`` and ``X-Secret-Key``, sends no gzip, and
  posts to ``<FI_BASE_URL>/tracer/v1/traces`` (traces only, no logs or metrics route);
* ``GrafiExporter`` maps Graphite's own attribute names to the ones Future AGI reads
  (``oi_span_type`` -> ``fi.span.kind``, ``input`` -> ``input.value``, ``output`` ->
  ``output.value``, ``conversation_id`` -> ``session.id``, ``user_id`` -> ``user.id``),
  leaves out empty ids and dict-valued attributes, and never exports a stack trace;
* by default only metadata leaves the process (see ``METADATA_ATTRIBUTES``). Set
  ``FI_CAPTURE_CONTENT=1`` (or ``capture_content=True``) to also export prompts, answers,
  tool arguments and results, and the text of an error.

It does not touch the global tracer provider, and it never calls Graphite's
``setup_tracing``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

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

# Graphite attribute -> the attribute Future AGI reads.
RENAMES = {
    "oi_span_type": "fi.span.kind",
    "input": "input.value",
    "output": "output.value",
    "conversation_id": "session.id",
    "user_id": "user.id",
}

# Graphite sets these to "" when the application gave no id. An empty id is not exported.
ID_ATTRIBUTES = frozenset({"session.id", "user.id"})

# Graphite writes the exception text, the traceback (local file paths) and a JSON copy of
# both onto the span. None of them is exported, in either mode. The text of the error is
# exported with content on, as ``error.message``.
NEVER_EXPORTED = frozenset({"error", "error.stack", "error.details"})

# Attributes that describe a call without containing what was said or done. Anything not
# listed here is dropped unless content capture is on, so an attribute added by a later
# Graphite release stays private until it is reviewed (tests/test_privacy.py checks this).
METADATA_ATTRIBUTES = frozenset(
    {
        # Graphite's own spans (after the renames above)
        "fi.span.kind",
        "session.id",
        "user.id",
        "id",
        "name",
        "type",
        "model",
        "invoke_id",
        "assistant_request_id",
        "subscribed_topics",
        "publish_to_topics",
        "error.type",
        # spans of an optional provider instrumentor (OpenInference OpenAI)
        "openinference.span.kind",
        "llm.model_name",
        "llm.provider",
        "llm.system",
    }
)
METADATA_PREFIXES = ("llm.token_count.",)

_TRUE = {"1", "true", "yes", "on"}


def map_attributes(attributes: Mapping[str, object] | None, capture_content: bool) -> dict[str, object]:
    """Rename Graphite's keys, drop what must not leave, and (without content) keep metadata only."""
    mapped: dict[str, object] = {}
    for key, value in (attributes or {}).items():
        if isinstance(value, Mapping):  # InvokeContext.kwargs: free-form application data
            continue
        if key in NEVER_EXPORTED:
            continue
        key = RENAMES.get(key, key)
        if key in ID_ATTRIBUTES and value in ("", None):
            continue
        if capture_content or key in METADATA_ATTRIBUTES or key.startswith(METADATA_PREFIXES):
            mapped[key] = value
    return mapped


def _map_event(event: Event, capture_content: bool) -> Event:
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


class _MappedSpan:
    """A read-only view of a finished span with Graphite's attributes mapped.

    Everything the OTLP encoder reads is delegated to the real span, except the
    attributes, the events and the status.
    """

    def __init__(self, span: ReadableSpan, capture_content: bool) -> None:
        self._span = span
        self._attributes = map_attributes(span.attributes, capture_content)
        self._events = tuple(_map_event(event, capture_content) for event in span.events)
        status = span.status
        description = status.description
        if status.status_code == StatusCode.ERROR and not capture_content:
            # The status message is the text of the exception. Keep the class name instead.
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


class GrafiExporter(SpanExporter):
    """Wrap an exporter so Graphite's spans arrive in the shape Future AGI reads."""

    def __init__(self, inner: SpanExporter, capture_content: bool = False) -> None:
        self._inner = inner
        self._capture_content = capture_content

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_MappedSpan(span, self._capture_content) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def create_tracer_provider(
    project_name: str | None = None,
    *,
    capture_content: bool | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    secret_key: str | None = None,
) -> TracerProvider:
    """Build the tracer provider that exports Graphite's spans to Future AGI.

    Use ``provider.get_tracer("grafi")`` as ``ExecutionServices(tracer=...)`` and call
    ``provider.shutdown()`` before the process exits so the last batch is flushed.
    """
    project_name = project_name or os.environ.get("FI_PROJECT_NAME") or "graphite-app"
    if capture_content is None:
        capture_content = os.environ.get("FI_CAPTURE_CONTENT", "").lower() in _TRUE
    base_url = (base_url or os.environ.get("FI_BASE_URL") or "https://api.futureagi.com").rstrip("/")
    api_key = api_key or os.environ.get("FI_API_KEY")
    secret_key = secret_key or os.environ.get("FI_SECRET_KEY")
    if not api_key or not secret_key:
        raise RuntimeError("Set FI_API_KEY and FI_SECRET_KEY: Future AGI needs both keys.")

    exporter = OTLPSpanExporter(
        endpoint=f"{base_url}/tracer/v1/traces",
        headers={"X-Api-Key": api_key, "X-Secret-Key": secret_key},
        compression=Compression.NoCompression,  # the Future AGI collector refuses gzip
    )
    provider = TracerProvider(
        resource=Resource.create({"project_name": project_name, "project_type": "observe"})
    )
    provider.add_span_processor(BatchSpanProcessor(GrafiExporter(exporter, capture_content)))
    return provider
