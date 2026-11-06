"""Send Mirascope traces to Future AGI.

Mirascope (``pip install "mirascope[openai,anthropic,google,ops]"``) already emits
OpenTelemetry spans: ``ops.instrument_llm()`` writes a GenAI ``chat <model>`` span for every
``llm.Model`` call and stream, and ``@ops.trace`` / ``ops.span`` / ``ops.session`` add spans of
your own. Mirascope does not take an endpoint, headers or a resource. You build the
OpenTelemetry tracer provider and hand it to ``ops.configure``. ``build_tracer_provider``
builds that provider:

* the resource carries ``project_name`` (Future AGI files spans by it) and ``project_type``;
* the OTLP/HTTP exporter carries ``X-Api-Key`` and ``X-Secret-Key``, sends no gzip, and posts
  to ``<FI_BASE_URL>/tracer/v1/traces`` (traces only, no logs or metrics). Mirascope's own
  ``examples/ops/configure_otlp.py`` uses the gRPC exporter with no headers and no resource,
  which Future AGI cannot accept, so this is not that example with values filled in;
* by default only metadata leaves the process (see ``METADATA_ATTRIBUTES``). Set
  ``FI_CAPTURE_CONTENT=1`` (or ``capture_content=True``) to also export prompts, answers, tool
  schemas, ``@ops.trace`` arguments and results, and the text of an error;
* a stack trace is never exported, in either mode: it holds local file paths.

Mirascope has no switch for content: ``instrument_llm`` always writes the messages onto the
span. ``ContentFilterExporter`` is the off switch.

Usage::

    provider = build_tracer_provider()
    ops.configure(tracer_provider=provider)
    ops.instrument_llm()
    ...
    provider.shutdown()   # flush now; the SDK also flushes at a normal interpreter exit
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Status, StatusCode

# Attributes on Mirascope's spans that describe a call without containing what was said or
# done. Anything not listed here is dropped unless content capture is on, so an attribute
# added by a later Mirascope release stays private until it is reviewed.
METADATA_ATTRIBUTES = frozenset(
    {
        # the model call (instrument_llm)
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.output.type",
        "gen_ai.request.temperature",
        "gen_ai.request.max_tokens",
        "gen_ai.request.top_p",
        "gen_ai.request.top_k",
        "gen_ai.request.frequency_penalty",
        "gen_ai.request.presence_penalty",
        "gen_ai.request.seed",
        "gen_ai.request.choice_count",
        "gen_ai.response.model",
        "gen_ai.response.id",
        "gen_ai.response.finish_reasons",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "mirascope.response.usage",
        "mirascope.response.cost",
        "mirascope.response.model_id",
        "mirascope.response.provider_id",
        "error.type",
        # the app's own tool span (see app.py): the tool's name, not its arguments or result
        "gen_ai.tool.name",
        # ops.trace / ops.span / ops.session (names of code, not data)
        "mirascope.type",
        "mirascope.fn.qualname",
        "mirascope.fn.module",
        "mirascope.fn.is_async",
        "mirascope.ops.session.id",
    }
)

# Never exported, even with content on: it holds absolute local file paths.
_NEVER_EXPORTED_EVENT_ATTRIBUTES = frozenset({"exception.stacktrace"})

_TRUE = {"1", "true", "yes", "on"}


def _filter_event(event: Event, capture_content: bool) -> Event:
    """Keep an event's name and time. An exception event keeps its type, and with content on
    its message; its stack trace is always dropped. Any other event keeps its attributes
    (``ops.span(...).info("...")`` messages, the untracked-parameters dump) only with
    content on."""
    attributes = dict(event.attributes or {})
    if event.name == "exception":
        keep = {"exception.type", "exception.message"} if capture_content else {"exception.type"}
        attributes = {key: value for key, value in attributes.items() if key in keep}
    elif not capture_content:
        attributes = {}
    else:
        attributes = {
            key: value
            for key, value in attributes.items()
            if key not in _NEVER_EXPORTED_EVENT_ATTRIBUTES
        }
    return Event(name=event.name, attributes=attributes, timestamp=event.timestamp)


def _filter_span(span: ReadableSpan, capture_content: bool) -> ReadableSpan:
    """A copy of a finished span with the content removed."""
    attributes = {
        key: value
        for key, value in (span.attributes or {}).items()
        if capture_content or key in METADATA_ATTRIBUTES
    }
    events = tuple(_filter_event(event, capture_content) for event in span.events)

    status = span.status
    description = status.description
    if status.status_code == StatusCode.ERROR and not capture_content:
        # The status text is str(exception). Keep the class name instead.
        description = next(
            (
                event.attributes["exception.type"]
                for event in events
                if event.attributes and "exception.type" in event.attributes
            ),
            None,
        )
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=events,
        links=span.links,
        kind=span.kind,
        status=Status(status.status_code, description),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class ContentFilterExporter(SpanExporter):
    """Wrap an exporter so that content, and always stack traces, never leave the process."""

    def __init__(self, inner: SpanExporter, capture_content: bool = False) -> None:
        self._inner = inner
        self._capture_content = capture_content

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_filter_span(span, self._capture_content) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def build_tracer_provider(
    project_name: str | None = None,
    *,
    capture_content: bool | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    secret_key: str | None = None,
) -> TracerProvider:
    """Build a tracer provider that exports Mirascope's spans to Future AGI.

    Pass the result to ``ops.configure(tracer_provider=...)``.
    """
    project_name = project_name or os.environ.get("FI_PROJECT_NAME") or "mirascope-app"
    if capture_content is None:
        capture_content = os.environ.get("FI_CAPTURE_CONTENT", "").lower() in _TRUE
    base_url = (base_url or os.environ.get("FI_BASE_URL") or "https://api.futureagi.com").rstrip("/")
    api_key = api_key or os.environ["FI_API_KEY"]
    secret_key = secret_key or os.environ["FI_SECRET_KEY"]

    exporter = OTLPSpanExporter(
        endpoint=f"{base_url}/tracer/v1/traces",
        headers={"X-Api-Key": api_key, "X-Secret-Key": secret_key},
        compression=Compression.NoCompression,  # optional: Future AGI cloud and self-hosted v1.56.0+ also accept gzip
    )

    provider = TracerProvider(
        resource=Resource.create({"project_name": project_name, "project_type": "observe"})
    )
    provider.add_span_processor(BatchSpanProcessor(ContentFilterExporter(exporter, capture_content)))
    return provider
