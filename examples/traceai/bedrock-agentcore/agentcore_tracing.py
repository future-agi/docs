"""Future AGI tracing for an agent hosted in Amazon Bedrock AgentCore Runtime.

Copy this file next to your agent. It is a recipe, not a package. It does three things the
runtime does not do for you once ADOT is disabled (``DISABLE_ADOT_OBSERVABILITY=true``):

1. ``keep_future_agi_exporter(provider)`` keeps the Future AGI exporter on a provider made by
   ``fi_instrumentation.register(..., set_global_tracer_provider=True)``. ``BedrockAgentCoreApp``
   adds its own ``BaggageSpanProcessor`` to the global provider (when the app is built, and again
   on a request after the global provider changed). ``register()`` marks its exporter as a replaceable default, and the first
   ``add_span_processor()`` call removes it, so without this line no span is exported. The
   exporter it adds is wrapped in ``ErrorTextExporter``: no stack trace is ever exported, and
   when traceAI's ``TraceConfig`` hides content (``FI_HIDE_INPUTS``, ``FI_HIDE_OUTPUTS``, ...)
   error spans keep the exception type name only. ``traceAI-langchain`` 0.2.0 writes LangChain's
   formatted traceback (with local file paths) into the status of failing spans whatever the
   ``FI_HIDE_*`` settings; this wrapper keeps it out of Future AGI.
2. ``traced_invocation(context, ...)`` opens one root span per invocation and copies the AgentCore
   session id (header ``X-Amzn-Bedrock-AgentCore-Runtime-Session-Id``, read by the SDK into
   ``context.session_id``) to ``session.id``: on the root span, in the traceAI context (so
   traceAI instrumentors stamp it on their spans) and in OpenTelemetry baggage (so a baggage
   span processor can stamp it on spans of a framework that uses its own OpenTelemetry tracer).
   When the request carries a W3C ``traceparent``, the root span links to the caller's span by
   default and starts its own trace. Pass ``join_caller_trace=True`` to make the caller's span the
   parent instead; do that only when the caller exports its spans to the same Future AGI project,
   because Future AGI lists a trace by a span that has no parent, and a parent that never reaches
   Future AGI hides the invocation from the trace list.
3. It flushes the provider after the root span ends, on success and on error, because the
   runtime can freeze or recycle the microVM after the response. The flush never raises.

The root span carries no prompt, no response and no error text. On error its status
description is the exception type name only.

For a framework that exports with its own OpenTelemetry SDK (the Strands example),
``ErrorTextExporter`` wraps the OTLP exporter the same way: never a stack trace, and with content
off the exception type name only, never the exception message.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager, nullcontext
from typing import Any, Iterable, Iterator, Optional, Sequence

from opentelemetry import baggage, propagate, trace
from opentelemetry import context as otel_context
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Link, SpanKind, Status, StatusCode

log = logging.getLogger("agentcore_tracing")

ROOT_SPAN_NAME = "agentcore.invocation"
TRACER_NAME = "agentcore_tracing"
SESSION_ATTRIBUTE = "session.id"
DEFAULT_FLUSH_TIMEOUT_MS = 5000
ERROR_TEXT_LIMIT = 500  # characters of exception message kept on an error span when content is on
TRACEBACK_MARKER = "Traceback (most recent call last)"
# traceAI TraceConfig switches (FI_HIDE_*) that hide prompt or response content. Error text can
# echo either, so any of them reduces error spans to the exception type name.
CONTENT_HIDE_FLAGS = (
    "hide_inputs",
    "hide_outputs",
    "hide_input_messages",
    "hide_output_messages",
    "hide_input_text",
    "hide_output_text",
)

try:  # traceAI context attributes are optional: the pure OpenTelemetry path does not need them.
    from fi_instrumentation import using_session as _using_session
except ImportError:  # pragma: no cover - exercised only without fi-instrumentation-otel
    _using_session = None


def keep_future_agi_exporter(provider: Any, span_exporter: Any = None, config: Any = None) -> Any:
    """Re-add Future AGI's exporter as a regular span processor. Call once, right after register().

    ``register()`` adds a ``BatchSpanProcessor`` and flags it as the provider's default. The
    Future AGI ``TracerProvider.add_span_processor()`` shuts a default processor down and drops
    it before adding the new one. Adding Future AGI's own ``BatchSpanProcessor`` here spends
    that one-time replacement while no span exists yet; every later processor (AgentCore's
    ``BaggageSpanProcessor``) is appended next to it. By default the exporter is built from
    FI_BASE_URL, FI_API_KEY and FI_SECRET_KEY exactly as ``register()`` builds it. If you gave
    ``register()`` your own ``span_exporter``, pass a new instance here: the replaced processor
    shuts its exporter down.

    The exporter is wrapped in ``ErrorTextExporter``: error spans never carry a stack trace, and
    when ``config`` (default: ``TraceConfig()``, which reads the ``FI_HIDE_*`` variables) hides
    content, they carry the exception type name only. If you pass a ``TraceConfig`` to the
    instrumentor, pass the same one here.
    """
    from fi_instrumentation import BatchSpanProcessor, HTTPSpanExporter

    exporter = span_exporter if span_exporter is not None else HTTPSpanExporter()
    exporter = ErrorTextExporter(exporter, type_only=content_hidden(config))
    provider.add_span_processor(BatchSpanProcessor(span_exporter=exporter))
    return provider


def content_hidden(config: Any = None) -> bool:
    """True when traceAI's ``TraceConfig`` hides prompt or response content.

    ``config`` defaults to ``TraceConfig()``, which reads ``FI_HIDE_INPUTS``, ``FI_HIDE_OUTPUTS``,
    ``FI_HIDE_INPUT_MESSAGES``, ``FI_HIDE_OUTPUT_MESSAGES``, ``FI_HIDE_INPUT_TEXT`` and
    ``FI_HIDE_OUTPUT_TEXT`` from the environment.
    """
    if config is None:
        from fi_instrumentation import TraceConfig

        config = TraceConfig()
    return any(bool(getattr(config, flag, False)) for flag in CONTENT_HIDE_FLAGS)


def strands_redaction_enabled() -> bool:
    """True when Strands' own content redaction is on (``gen_ai_unredacted_attributes=`` is set)."""
    tokens = os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN", "").split(",")
    return any(t.strip().startswith("gen_ai_unredacted_attributes=") for t in tokens)


def _type_name(qualified: Optional[str]) -> str:
    return (str(qualified) if qualified else "Error").rsplit(".", 1)[-1] or "Error"


_REPR_TYPE = re.compile(r"\s*([A-Za-z_][\w.]*)\(")


def _without_traceback(text: Any) -> str:
    """Error text cut before a formatted Python traceback, at most ERROR_TEXT_LIMIT characters."""
    return str(text or "").split(TRACEBACK_MARKER, 1)[0].strip()[:ERROR_TEXT_LIMIT]


def _exception_event(event: Event, type_only: bool) -> Event:
    attributes = event.attributes or {}
    if type_only:
        return Event("exception", {"exception.type": _type_name(attributes.get("exception.type"))}, event.timestamp)
    kept = {"exception.type": str(attributes.get("exception.type") or "Error")}
    message = _without_traceback(attributes.get("exception.message"))
    if message:
        kept["exception.message"] = message
    if "exception.escaped" in attributes:
        kept["exception.escaped"] = attributes["exception.escaped"]
    return Event("exception", kept, event.timestamp)  # never exception.stacktrace


def _safe_error_span(span: ReadableSpan, type_only: bool) -> ReadableSpan:
    if span.instrumentation_scope is not None and span.instrumentation_scope.name == TRACER_NAME:
        return span  # the recipe's own root span already carries the exception type name only
    exception_events = [e for e in span.events if e.name == "exception"]
    if span.status.status_code is not StatusCode.ERROR and not exception_events:
        return span
    description = span.status.description or ""
    exc_type = next(
        (e.attributes.get("exception.type") for e in exception_events if e.attributes and e.attributes.get("exception.type")),
        None,
    )
    if exc_type is None:  # LangChain's run.error starts with repr(error): "ValueError('...')"
        match = _REPR_TYPE.match(description)
        exc_type = match.group(1) if match else None
    events = [_exception_event(e, type_only) if e.name == "exception" else e for e in span.events]
    if span.status.status_code is StatusCode.ERROR:
        text = _type_name(exc_type) if type_only else (_without_traceback(description) or _type_name(exc_type))
        status = Status(StatusCode.ERROR, text)
    else:
        status = span.status
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


class ErrorTextExporter(SpanExporter):
    """Wrap a span exporter so error spans never carry a stack trace.

    Frameworks put error text where content settings do not reach it: ``traceAI-langchain``
    0.2.0 writes LangChain's ``run.error`` (``repr(error)`` plus the formatted traceback, with
    local file paths) into the span status, and ``record_exception`` adds an ``exception`` event
    with ``exception.stacktrace``; Strands writes ``str(exception)`` into the status and records
    the same event, even with its content redaction on.

    ``type_only=True`` (content off): the status description becomes the exception type name
    (from the recorded ``exception`` event, else the ``Type(`` prefix of the description, else
    ``Error``) and exception events keep ``exception.type`` only.
    ``type_only=False`` (content on): the status keeps the error text up to the first
    ``Traceback (most recent call last)``, at most ``ERROR_TEXT_LIMIT`` characters; exception
    events keep type, message (cut the same way) and ``exception.escaped``.
    In both modes ``exception.stacktrace`` is dropped. Spans without an error pass through
    unchanged, and so does the recipe's own root span.
    """

    def __init__(self, exporter: SpanExporter, type_only: bool = True) -> None:
        self._exporter = exporter
        self.type_only = type_only

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._exporter.export([_safe_error_span(s, self.type_only) for s in spans])

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)


class ErrorTypeOnlyExporter(ErrorTextExporter):
    """``ErrorTextExporter(exporter, type_only=True)``: error spans carry the exception type name only."""

    def __init__(self, exporter: SpanExporter) -> None:
        super().__init__(exporter, type_only=True)


def _request_headers(context: Any) -> Any:
    request = getattr(context, "request", None)
    headers = getattr(request, "headers", None)
    return headers if headers is not None else {}


def flush(provider: Any, timeout_millis: int = DEFAULT_FLUSH_TIMEOUT_MS) -> bool:
    """Flush buffered spans. Never raises. Returns False when the flush failed or timed out."""
    if provider is None or not hasattr(provider, "force_flush"):
        return False
    try:
        return bool(provider.force_flush(timeout_millis))
    except Exception as exc:  # tracing must never fail the invocation
        log.warning("span flush failed (%s); spans of this invocation may be lost", type(exc).__name__)
        return False


def _start_root(context: Any, provider: Any, name: str, join_caller_trace: bool):
    """Caller context (traceparent, baggage) + session id, then the root span (not yet current)."""
    session_id = getattr(context, "session_id", None)
    current = otel_context.get_current()
    ambient = trace.get_current_span(current)
    extracted = propagate.extract(_request_headers(context), context=current)
    caller = trace.get_current_span(extracted).get_span_context()
    links = []
    if join_caller_trace:
        parent = extracted
    else:  # keep the request's baggage and the ambient span (normally none); link to the caller
        parent = trace.set_span_in_context(ambient, extracted)
        if caller.is_valid and caller != ambient.get_span_context():
            links = [Link(caller)]
    if session_id:
        parent = baggage.set_baggage(SESSION_ATTRIBUTE, session_id, context=parent)
    tracer_provider = provider if provider is not None else trace.get_tracer_provider()
    attributes = {"fi.span.kind": "CHAIN"}
    if session_id:
        attributes[SESSION_ATTRIBUTE] = session_id
    root = tracer_provider.get_tracer(TRACER_NAME).start_span(
        name, context=parent, kind=SpanKind.SERVER, attributes=attributes, links=links,
        record_exception=False, set_status_on_exception=False,
    )
    return root, trace.set_span_in_context(root, parent), session_id, tracer_provider


def _session_scope(session_id: Optional[str]):
    return _using_session(session_id) if (session_id and _using_session) else nullcontext()


@contextmanager
def traced_invocation(
    context: Any,
    provider: Any = None,
    *,
    name: str = ROOT_SPAN_NAME,
    join_caller_trace: bool = False,
    flush_timeout_millis: int = DEFAULT_FLUSH_TIMEOUT_MS,
) -> Iterator[trace.Span]:
    """Wrap one AgentCore invocation: root span, caller trace, session id, flush.

    ``context`` is the ``RequestContext`` that ``BedrockAgentCoreApp`` passes to an entrypoint
    declared as ``def handler(payload, context)``. ``provider`` is the tracer provider to take the
    root span's tracer from and to flush; ``None`` uses the global provider. Works in a plain
    function, an ``async def`` entrypoint and an async generator entrypoint (AgentCore runs those
    in one task). For a plain (sync) generator entrypoint use ``traced_stream``.
    """
    root, current, session_id, tracer_provider = _start_root(context, provider, name, join_caller_trace)
    token = otel_context.attach(current)
    try:
        with _session_scope(session_id):
            try:
                yield root
            except BaseException as exc:
                root.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise
    finally:
        otel_context.detach(token)
        root.end()
        flush(tracer_provider, flush_timeout_millis)


def traced_stream(
    context: Any,
    chunks: Iterable[Any],
    provider: Any = None,
    *,
    name: str = ROOT_SPAN_NAME,
    join_caller_trace: bool = False,
    flush_timeout_millis: int = DEFAULT_FLUSH_TIMEOUT_MS,
) -> Iterator[Any]:
    """``traced_invocation`` for a sync streaming entrypoint: ``return traced_stream(context, gen)``.

    AgentCore iterates a sync generator from a thread pool, one step per call and each step in
    its own copy of the request context, so a span made current in one step is not current in
    the next. This wrapper makes the root span current again around every step, ends it after
    the last chunk (or when the client goes away) and then flushes.
    """
    root, current, session_id, tracer_provider = _start_root(context, provider, name, join_caller_trace)
    iterator = iter(chunks)
    try:
        while True:
            token = otel_context.attach(current)
            try:
                with _session_scope(session_id):
                    chunk = next(iterator)
            except StopIteration:
                return
            except BaseException as exc:
                root.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise
            finally:
                otel_context.detach(token)
            yield chunk
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                pass
        root.end()
        flush(tracer_provider, flush_timeout_millis)
