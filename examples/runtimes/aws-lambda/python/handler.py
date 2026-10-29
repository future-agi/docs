"""Example Lambda handler: one invocation is one trace, flushed before the handler returns."""
import json

from opentelemetry.trace import SpanKind, Status, StatusCode

import tracing

tracing.init()  # once per execution environment, outside the handler


def lookup_order(order_id, note):
    """The 'work'. Raises for order id 'boom' so the failure path can be shown."""
    with tracing.tracer().start_as_current_span(
        "lookup_order", attributes={"fi.span.kind": "TOOL", "tool.name": "lookup_order"},
        record_exception=False, set_status_on_exception=False,
    ) as span:
        capture = tracing.capture_content()
        if capture:
            span.set_attribute("input.value", tracing.dumps({"order_id": order_id, "note": note}))
        try:
            if order_id == "boom":
                raise ValueError(f"order lookup failed: {note}")
            result = {"order_id": order_id, "status": "shipped", "note": note}
        except Exception as exc:
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(Status(StatusCode.ERROR, str(exc) if capture else type(exc).__name__))
            raise
        if capture:
            span.set_attribute("output.value", tracing.dumps(result))
        return result


def _invoke(event, context):
    parent = tracing.extract_parent(event)  # None unless an API Gateway v2 / function URL traceparent
    attrs = {
        "fi.span.kind": "CHAIN",
        "faas.coldstart": tracing.take_cold_start(),
        "faas.trigger": tracing.trigger(event),
    }
    request_id = getattr(context, "aws_request_id", None)
    if request_id:
        attrs["faas.invocation_id"] = request_id
    with tracing.tracer().start_as_current_span(
        "lambda.handler", context=parent, kind=SpanKind.SERVER, attributes=attrs,
        record_exception=False, set_status_on_exception=False,
    ) as span:
        capture = tracing.capture_content()
        if capture:
            span.set_attribute("input.value", tracing.dumps(event))
        try:
            ev = event if isinstance(event, dict) else {}
            records = ev.get("Records")
            body = records[0].get("body") if records else ev.get("body")  # SQS first record, else HTTP body
            payload = json.loads(body) if isinstance(body, str) else ev
            result = lookup_order(payload.get("order_id", "unknown"), payload.get("note", ""))
        except Exception as exc:
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(Status(StatusCode.ERROR, str(exc) if capture else type(exc).__name__))
            if capture:  # message only: no stack trace, which would carry file paths
                span.add_event("exception", {"exception.type": type(exc).__name__, "exception.message": str(exc)})
            raise
        if capture:
            span.set_attribute("output.value", tracing.dumps(result))
        return result


def lambda_handler(event, context):
    try:
        return _invoke(event, context)
    finally:
        # The root span has ended. Flush on the success path and on the error path, before the
        # runtime freezes the environment.
        tracing.flush(context)
