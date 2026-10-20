"""Client path: the OpenAI client pointed at the documented TrueFoundry base URL, traced by traceai-openai.

No network. The gateway is a mock transport answering at https://gateway.truefoundry.ai, so these
tests prove what the instrumentor records for the request shape the TrueFoundry docs describe
(POST /chat/completions at the root, `provider_account/model_name`, Bearer token). They do not
prove anything about the real gateway.
"""
import json

import pytest

try:
    import httpx2 as httpx
except ImportError:  # openai 1.x and 2.x use httpx
    import httpx

from fi_instrumentation import TraceConfig
from openai import OpenAI
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from traceai_openai import OpenAIInstrumentor

BASE_URL = "https://gateway.truefoundry.ai"
MODEL = "openai-main/gpt-4o-mini"
PROVIDER_MODEL = "gpt-4o-mini-2024-07-18"
PROMPT_MARK = "PROMPTMARK-7f3a"
ANSWER_MARK = "ANSWERMARK-91bc"


def _gateway(request: "httpx.Request") -> "httpx.Response":
    assert request.method == "POST"
    assert request.url.host == "gateway.truefoundry.ai"
    assert request.url.path == "/chat/completions"
    assert request.headers["authorization"] == "Bearer tfy-test-token"
    body = json.loads(request.content)
    if body["model"] == "openai-main/forbidden":
        # Body shape captured from the real gateway on 2026-10-20 (the e-mail is a placeholder).
        return httpx.Response(
            403,
            json={
                "status": "failure",
                "message": "User dev@example.test is not authorized to access model openai-main/forbidden or model does not exist",
                "error": {
                    "message": "User dev@example.test is not authorized to access model openai-main/forbidden or model does not exist",
                    "type": "AuthorizationError",
                    "code": "403",
                },
                "error_origin_level": "authorization",
            },
        )
    if body.get("stream"):
        chunks = [
            {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": PROVIDER_MODEL,
             "choices": [{"index": 0, "delta": {"role": "assistant", "content": ANSWER_MARK}, "finish_reason": None}]},
            {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": PROVIDER_MODEL,
             "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": PROVIDER_MODEL, "choices": [],
             "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}},
        ]
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": PROVIDER_MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER_MARK}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        },
    )


@pytest.fixture()
def traced(request):
    config = getattr(request, "param", None)
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=provider, **({"config": config} if config else {}))
    client = OpenAI(
        base_url=BASE_URL,
        api_key="tfy-test-token",
        http_client=httpx.Client(transport=httpx.MockTransport(_gateway)),
    )
    yield client, exporter
    instrumentor.uninstrument()


def _ask(client, model=MODEL):
    return client.chat.completions.create(model=model, messages=[{"role": "user", "content": PROMPT_MARK}])


def test_success_span_has_model_tokens_and_provider(traced):
    client, exporter = traced
    _ask(client)
    (span,) = exporter.get_finished_spans()
    attrs = dict(span.attributes)
    assert span.name == "ChatCompletion"
    assert span.status.status_code == StatusCode.OK
    assert attrs["gen_ai.span.kind"] == "LLM"
    # The model on the span is the one the gateway answered with, when it answers with one.
    assert attrs["gen_ai.request.model"] == PROVIDER_MODEL
    # The id the client sent, `provider_account/model_name`, stays in the request parameters.
    assert json.loads(attrs["gen_ai.request.parameters"])["model"] == MODEL
    assert (attrs["gen_ai.usage.input_tokens"], attrs["gen_ai.usage.output_tokens"], attrs["gen_ai.usage.total_tokens"]) == (11, 5, 16)
    # traceai-openai 0.1.10 recognises api.openai.com, openai.azure.com and googleapis.com by host.
    # Any other host, including gateway.truefoundry.ai, gets the fallback label.
    assert attrs["gen_ai.provider.name"] == "openai"


def test_gateway_403_is_an_error_span_without_a_model_attribute(traced):
    client, exporter = traced
    with pytest.raises(Exception) as err:
        _ask(client, "openai-main/forbidden")
    assert type(err.value).__name__ == "PermissionDeniedError"
    (span,) = exporter.get_finished_spans()
    assert span.status.status_code == StatusCode.ERROR
    assert "PermissionDeniedError" in span.status.description
    assert [e.name for e in span.events] == ["exception"]
    attrs = dict(span.attributes)
    # traceai-openai 0.1.10 sets no model attribute on a failed call; the id is only in the parameters.
    assert "gen_ai.request.model" not in attrs
    assert json.loads(attrs["gen_ai.request.parameters"])["model"] == "openai-main/forbidden"


def test_content_is_captured_by_default(traced):
    client, exporter = traced
    _ask(client)
    blob = json.dumps(dict(exporter.get_finished_spans()[0].attributes))
    assert PROMPT_MARK in blob and ANSWER_MARK in blob


@pytest.mark.parametrize(
    "traced",
    [TraceConfig(hide_inputs=True, hide_outputs=True, hide_input_messages=True, hide_output_messages=True)],
    indirect=True,
)
def test_hide_switches_remove_prompt_and_response_but_keep_usage(traced):
    client, exporter = traced
    _ask(client)
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    blob = json.dumps(attrs)
    assert PROMPT_MARK not in blob and ANSWER_MARK not in blob
    assert attrs["gen_ai.usage.total_tokens"] == 16
    assert attrs["gen_ai.request.model"] == PROVIDER_MODEL


@pytest.mark.parametrize(
    "traced",
    [TraceConfig(hide_inputs=True, hide_outputs=True, hide_input_messages=True, hide_output_messages=True)],
    indirect=True,
)
def test_hide_switches_do_not_cover_error_text(traced):
    """Known limitation, pinned so a fix upstream shows up here: the failure path keeps the error text."""
    client, exporter = traced
    with pytest.raises(Exception):
        _ask(client, "openai-main/forbidden")
    (span,) = exporter.get_finished_spans()
    assert "not authorized" in span.status.description
    # The real gateway puts the caller's e-mail in that text (seen live on 2026-10-20), so it is stored.
    assert "dev@example.test" in span.status.description
    (event,) = span.events
    assert "exception.stacktrace" in event.attributes


def test_stream_span_has_tokens_but_no_model_on_traceai_openai_0_1_10(traced):
    """Seen against the real gateway on 2026-10-20: a streamed call records usage but no model attribute.

    Fixed in unreleased traceAI PR #249; this test is meant to go red on a build that has it.
    """
    from client_example import run_stream

    client, exporter = traced
    assert run_stream(client, MODEL, PROMPT_MARK) == ANSWER_MARK
    (span,) = exporter.get_finished_spans()
    attrs = dict(span.attributes)
    assert span.status.status_code != StatusCode.ERROR
    assert attrs["gen_ai.usage.total_tokens"] == 16
    assert "gen_ai.request.model" not in attrs
