"""SYNTHETIC OTLP trace batches shaped like a TrueFoundry AI Gateway export.

These are NOT captured from a TrueFoundry gateway. They are built from the
attribute names TrueFoundry documents, so the Future AGI side of the native
export can be tested without a TrueFoundry tenant:

  * tfy.* attributes:    https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes
  * gen_ai.* dual-write: https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes-genai
                         (off by default, needs ENABLE_GEN_AI_OTEL_ATTRIBUTES=true on tfy-llm-gateway)
  * service.name:        tfy-llm-gateway, https://www.truefoundry.com/docs/ai-gateway/honeycomb
  * Additional Resource Attributes (UI field): https://www.truefoundry.com/docs/ai-gateway/arize

What is assumed, because the TrueFoundry docs do not say:
  * a request is one root `ChatCompletion` span with one `Model: <model>` child
  * which gen_ai.* attributes sit on the root span and which on the model span
  * the exact JSON of gen_ai.input.messages and gen_ai.output.messages
  * that a failed request has OTLP status ERROR (the docs only name tfy.error_type
    and tfy.error_message)
  * what Exclude Request Data does beyond removing tfy.input, tfy.output and
    tfy.input_short_hand ("exclude_literal" keeps everything else on purpose)
"""
import json
import time
import uuid
from typing import Dict, Iterable, Optional

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span, Status

ACCOUNT_MODEL = "openai-main/gpt-4o-mini"
PROVIDER_MODEL = "gpt-4o-mini-2024-07-18"
CONTENT_KEYS = ("tfy.input", "tfy.output", "tfy.input_short_hand")


def _val(v) -> AnyValue:
    if isinstance(v, bool):
        return AnyValue(bool_value=v)
    if isinstance(v, int):
        return AnyValue(int_value=v)
    if isinstance(v, float):
        return AnyValue(double_value=v)
    if isinstance(v, (list, tuple)):
        return AnyValue(array_value=ArrayValue(values=[_val(x) for x in v]))
    return AnyValue(string_value=str(v))


def _kvs(attrs: Dict[str, object]) -> Iterable[KeyValue]:
    return [KeyValue(key=k, value=_val(v)) for k, v in attrs.items() if v is not None]


def build_batch(
    marker: str = "MARKER",
    *,
    genai: bool = True,
    content: str = "on",
    failure: bool = False,
    resource_attrs: Optional[Dict[str, str]] = None,
    error_status: bool = True,
    exception_event: bool = False,
    trace_id: Optional[bytes] = None,
    service_name: str = "tfy-llm-gateway",
) -> ExportTraceServiceRequest:
    """Build one request: ChatCompletion root plus Model child.

    genai:   include the gen_ai.* dual-write attributes (gateway flag on).
    content: "on"             tfy.input/output/input_short_hand present, and gen_ai.*.messages if genai
             "exclude_literal" Exclude Request Data read literally: only the three tfy.* keys
                              are removed; gen_ai.*.messages stay (worst case, not a TrueFoundry claim)
             "off"            no prompt or response content in any attribute
    failure: the request was rejected (403, tfy-forbidden)
    error_status: on failure, also set OTLP status ERROR (assumed, see above); False leaves the
             status unset so only tfy.error_type and error.type mark the failure
    exception_event: on failure, add an OTel "exception" event with message and stack trace
             (synthetic: nothing documents that the gateway records one)
    resource_attrs: extra resource attributes, as the Additional Resource Attributes field would add
    The marker is placed in the prompt, the response, request metadata, the subject (as
    an e-mail local part, lower-cased) and, for failures, the error message and status
    message, so a case-insensitive scan can see which attributes carry it. Ids never contain it.
    """
    assert content in ("on", "exclude_literal", "off")
    tid = trace_id or uuid.uuid4().bytes
    root_id, model_id = uuid.uuid4().bytes[:8], uuid.uuid4().bytes[:8]
    start = time.time_ns() - 900_000_000
    mid = start + 120_000_000
    end = start + 800_000_000

    conv = f"conv-{uuid.uuid4().hex[:12]}"
    prompt = f"Summarise ticket {marker} for the on-call engineer."
    answer = f"Ticket {marker}: customer cannot log in since 09:00 UTC."
    request_body = json.dumps({"model": ACCOUNT_MODEL, "messages": [{"role": "user", "content": prompt}]})
    response_body = json.dumps({"choices": [{"message": {"role": "assistant", "content": answer}}]})
    subject = f"user:{marker.lower()}@example.test"
    metadata = json.dumps({"ticket": marker})

    root: Dict[str, object] = {
        "tfy.span_type": "ChatCompletion",
        "tfy.data_routing.destination": "default",
        "tfy.request.created_by_subject": subject,
        "tfy.request.model_name": ACCOUNT_MODEL,
        "tfy.request.metadata": metadata,
        "tfy.request.conversation_id": conv,
        "tfy.request.created_by_subject_teams": [f"team-{marker.lower()}"],
        "tfy.prompt_variables": json.dumps({"ticket": marker}),
        "http.response.status_code": 403 if failure else 200,
    }
    model: Dict[str, object] = {
        "tfy.span_type": "Model",
        "tfy.model.name": ACCOUNT_MODEL,
        "tfy.model.fqn": f"model:truefoundry/{ACCOUNT_MODEL}",
        "tfy.model.request_url": "https://api.openai.com/v1/chat/completions",
        "tfy.model.streaming": False,
        "tfy.model.request_type": "ChatCompletion",
        "tfy.request.created_by_subject": subject,
        "http.response.status_code": 403 if failure else 200,
    }
    if not failure:
        model.update(
            {
                "tfy.model.metric.input_tokens": 34,
                "tfy.model.metric.output_tokens": 19,
                "tfy.model.metric.latency_in_ms": 680,
                "tfy.model.metric.cost_in_usd": 0.0000216,
            }
        )
    else:
        for attrs in (root, model):
            attrs["tfy.error_type"] = "tfy-forbidden"
            attrs["tfy.error_message"] = f"not authorized to use model for ticket {marker}"

    if content != "off":
        for attrs in (root, model):
            attrs["tfy.input"] = request_body
            attrs["tfy.input_short_hand"] = prompt[:40]
            if not failure:
                attrs["tfy.output"] = response_body
        if content == "exclude_literal":
            for attrs in (root, model):
                for key in CONTENT_KEYS:
                    attrs.pop(key, None)

    if genai:
        root.update(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.workflow.name": "ChatCompletion",
                "gen_ai.conversation.id": conv,
            }
        )
        model.update(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "openai",
                "gen_ai.workflow.name": "Model",
                "gen_ai.request.model": ACCOUNT_MODEL,
                "gen_ai.request.max_tokens": 256,
                "gen_ai.request.temperature": 0.2,
                "server.address": "api.openai.com",
                "server.port": 443,
            }
        )
        if failure:
            for attrs in (root, model):
                attrs["error.type"] = "tfy-forbidden"
        else:
            model.update(
                {
                    "gen_ai.response.model": PROVIDER_MODEL,
                    "gen_ai.response.id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                    "gen_ai.response.finish_reasons": ["stop"],
                    "gen_ai.usage.input_tokens": 34,
                    "gen_ai.usage.output_tokens": 19,
                    "gen_ai.usage.total_tokens": 53,
                }
            )
        if content != "off":
            in_msgs = json.dumps([{"role": "user", "parts": [{"type": "text", "content": prompt}]}])
            out_msgs = json.dumps(
                [{"role": "assistant", "parts": [{"type": "text", "content": answer}], "finish_reason": "stop"}]
            )
            for attrs in (root, model):
                attrs["gen_ai.input.messages"] = in_msgs
                if not failure:
                    attrs["gen_ai.output.messages"] = out_msgs

    status = (
        Status(code=Status.STATUS_CODE_ERROR, message=f"request failed for {marker}")
        if failure and error_status
        else Status()
    )
    spans = [
        Span(
            trace_id=tid,
            span_id=root_id,
            name="ChatCompletion",
            kind=Span.SPAN_KIND_SERVER,
            start_time_unix_nano=start,
            end_time_unix_nano=end,
            attributes=_kvs(root),
            status=status,
        ),
        Span(
            trace_id=tid,
            span_id=model_id,
            parent_span_id=root_id,
            name=f"Model: {ACCOUNT_MODEL}",
            kind=Span.SPAN_KIND_CLIENT,
            start_time_unix_nano=mid,
            end_time_unix_nano=end - 20_000_000,
            attributes=_kvs(model),
            status=status,
        ),
    ]
    if failure and exception_event:
        spans[1].events.add(
            time_unix_nano=end - 30_000_000,
            name="exception",
            attributes=_kvs(
                {
                    "exception.type": "ForbiddenError",
                    "exception.message": f"not authorized to use model for ticket {marker}",
                    "exception.stacktrace": "Error: forbidden\n    at handler (/srv/tfy-llm-gateway/dist/server.js:10:5)",
                }
            ),
        )
    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    res_attrs: Dict[str, object] = {"service.name": service_name}
    res_attrs.update(resource_attrs or {})
    rs.resource.attributes.extend(_kvs(res_attrs))
    ss = rs.scope_spans.add()
    ss.scope.name = "tfy-llm-gateway"
    ss.spans.extend(spans)
    return req
