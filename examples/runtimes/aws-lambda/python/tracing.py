"""Tracing lifecycle for an AWS Lambda function: copy this file next to your handler.

    init once (import time)  ->  one root span per invocation  ->  flush before every return

Nothing here calls AWS. Environment (set it on the function, keep the keys in Secrets Manager or
an encrypted variable, never in the source):

    FI_API_KEY, FI_SECRET_KEY   both are required; if either is missing tracing is switched off
    FI_BASE_URL                 default https://api.futureagi.com   (self-hosted: your own URL)
    FI_PROJECT_NAME             the Observe project (default: the function name)
    LAMBDA_TRACE_CAPTURE_CONTENT=true   opt in to the event, result and error text on spans (off by default)
"""
import json
import logging
import os
import threading

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

log = logging.getLogger("lambda_tracing")

FLUSH_BUDGET_S = 2.0     # proposed upper bound for one flush; a proposal, not a measurement
FLUSH_RESERVE_S = 0.25   # always leave this much of the remaining Lambda time unused

_provider = None
_cold = True
providers_built = 0      # the tests assert this stays at 1 across invocations


def capture_content() -> bool:
    return os.environ.get("LAMBDA_TRACE_CAPTURE_CONTENT", "").lower() == "true"


def build_provider(span_exporter=None, set_global=True) -> TracerProvider:
    """Build the provider. Called once per execution environment, never per invocation."""
    global providers_built
    providers_built += 1
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    attrs = {
        "project_name": os.environ.get("FI_PROJECT_NAME") or function_name or "aws-lambda",
        "project_type": "observe",
    }
    attrs["service.name"] = attrs["project_name"]
    if function_name:  # only when the runtime provides it; never invented
        attrs["faas.name"] = function_name
    provider = TracerProvider(resource=Resource.create(attrs))

    api_key, secret_key = os.environ.get("FI_API_KEY"), os.environ.get("FI_SECRET_KEY")
    if span_exporter is None and api_key and secret_key:
        base = os.environ.get("FI_BASE_URL", "https://api.futureagi.com").rstrip("/")
        span_exporter = OTLPSpanExporter(
            endpoint=f"{base}/tracer/v1/traces",
            headers={"X-Api-Key": api_key, "X-Secret-Key": secret_key},
            timeout=int(FLUSH_BUDGET_S),   # bounds the exporter's own retries
            compression=Compression.NoCompression,  # Future AGI rejects gzip bodies
        )
    elif span_exporter is None:
        log.warning("FI_API_KEY / FI_SECRET_KEY not set: tracing is off, spans are not exported")
    if span_exporter is not None:
        # Batch processor + an explicit force_flush before return. Never wait for its timer: the
        # environment is frozen after the handler returns.
        provider.add_span_processor(BatchSpanProcessor(span_exporter, schedule_delay_millis=60_000))
    if set_global:
        trace.set_tracer_provider(provider)
    return provider


def init(span_exporter=None, set_global=True) -> TracerProvider:
    """Idempotent: the first call builds the provider, later calls return it."""
    global _provider
    if _provider is None:
        _provider = build_provider(span_exporter, set_global)
    return _provider


def reset_for_tests():
    global _provider, _cold, providers_built
    _provider, _cold, providers_built = None, True, 0


def tracer():
    return init().get_tracer("lambda-handler")


def take_cold_start() -> bool:
    """True for the first invocation of this execution environment only."""
    global _cold
    cold, _cold = _cold, False
    return cold


def extract_parent(event):
    """W3C traceparent from an API Gateway HTTP API (payload v2) or Lambda function URL event.

    Header names are lower-cased by those two event shapes. SQS, SNS, EventBridge, ALB, REST API
    (payload v1) and X-Ray-only carriers are NOT read: those invocations start a new trace.
    """
    if not isinstance(event, dict) or event.get("version") != "2.0":
        return None
    headers = event.get("headers")
    if not isinstance(headers, dict) or not headers.get("traceparent"):
        return None
    return TraceContextTextMapPropagator().extract({"traceparent": headers["traceparent"]})


def trigger(event) -> str:
    if isinstance(event, dict) and event.get("version") == "2.0" and "requestContext" in event:
        return "http"
    return "other"


def flush(context=None) -> bool:
    """Flush before the handler returns. Never raises, never outlives the invocation."""
    try:
        budget = FLUSH_BUDGET_S
        remaining = getattr(context, "get_remaining_time_in_millis", None)
        if remaining:
            budget = min(budget, remaining() / 1000 - FLUSH_RESERVE_S)
        if budget <= 0:
            log.warning("flush skipped: not enough invocation time left, spans of this invocation are lost")
            return False
        # BatchSpanProcessor.force_flush only checks its deadline between exports: a slow collector
        # can hold it for the exporter's full timeout. Run it on a helper thread and stop waiting at
        # the budget, so the handler returns on time either way.
        result = []
        t = threading.Thread(target=lambda: result.append(init().force_flush(timeout_millis=int(budget * 1000))), daemon=True)
        t.start()
        t.join(budget)
        done = bool(result and result[0])
        if not done:
            log.warning("flush did not complete within %.2fs, spans of this invocation may be lost", budget)
        return bool(done)
    except Exception as exc:  # tracing must never fail the invocation
        log.warning("flush failed (%s), spans of this invocation are lost", type(exc).__name__)
        return False


def dumps(value) -> str:
    return json.dumps(value, default=str)[:4000]
