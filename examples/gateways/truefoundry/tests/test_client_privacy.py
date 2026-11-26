"""Released client privacy and model coverage, with real SDKs and no vendor traffic."""
import asyncio
import gzip
import json

import pytest
from openai import AsyncOpenAI, OpenAI, PermissionDeniedError
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from traceai_openai import OpenAIInstrumentor

from post_batch import post_http, to_otlp_json
from test_client_tracing import ANSWER_MARK, BASE_URL, MODEL, PROMPT_MARK, _gateway, httpx
from test_page_snippet import PRIVACY_FLAGS, receiver


@pytest.fixture()
def private_tracing(monkeypatch, request):
    error_only = getattr(request, "param", None) == "error-only"
    for flag in PRIVACY_FLAGS:
        monkeypatch.setenv(flag, str(not error_only or flag == "FI_HIDE_ERROR_DETAILS").lower())
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        yield exporter
    finally:
        instrumentor.uninstrument()
        provider.shutdown()


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("mode", ["success", "stream", "error"])
def test_private_client_semantics(private_tracing, asynchronous, mode):
    kwargs = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT_MARK}]}
    if mode == "error":
        kwargs["model"] = "openai-main/forbidden"
    if mode == "stream":
        kwargs.update(stream=True, stream_options={"include_usage": True})

    async def async_call():
        async with AsyncOpenAI(base_url=BASE_URL, api_key="tfy-test-token", max_retries=0,
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(_gateway))) as client:
            response = await client.chat.completions.create(**kwargs)
            if mode == "stream":
                async for _ in response:
                    pass

    def sync_call():
        with OpenAI(base_url=BASE_URL, api_key="tfy-test-token", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(_gateway))) as client:
            response = client.chat.completions.create(**kwargs)
            if mode == "stream":
                list(response)

    def call():
        return asyncio.run(async_call()) if asynchronous else sync_call()

    if mode == "error":
        with pytest.raises(PermissionDeniedError):
            call()
    else:
        call()
    (span,) = private_tracing.get_finished_spans()
    assert span.attributes["gen_ai.request.model"] == ("gpt-4o-mini-2024-07-18" if mode == "success" else kwargs["model"])
    assert span.attributes["gen_ai.provider.name"] == "openai"
    assert "gen_ai.request.parameters" not in span.attributes
    for marker in (PROMPT_MARK, ANSWER_MARK, "dev@example.test", "tfy-test-token"):
        assert marker not in span.to_json()
    if mode == "error":
        assert span.status.status_code == StatusCode.ERROR
        assert span.status.description is None
        (event,) = span.events
        assert event.attributes["exception.type"].endswith("PermissionDeniedError")
        assert "exception.message" not in event.attributes
        assert "exception.stacktrace" not in event.attributes
    else:
        assert span.attributes["gen_ai.usage.total_tokens"] == 16


@pytest.mark.parametrize("private_tracing", ["error-only"], indirect=True)
def test_error_hiding_can_be_enabled_without_hiding_content(private_tracing):
    with OpenAI(base_url=BASE_URL, api_key="tfy-test-token", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(_gateway))) as client:
        with pytest.raises(PermissionDeniedError):
            client.chat.completions.create(model="openai-main/forbidden", messages=[{"role": "user", "content": PROMPT_MARK}])
    (span,) = private_tracing.get_finished_spans()
    assert span.status.status_code == StatusCode.ERROR
    assert PROMPT_MARK in span.to_json()
    assert span.status.description is None
    assert "dev@example.test" not in span.to_json()
    assert "exception.stacktrace" not in span.to_json()
    assert "PermissionDeniedError" in span.to_json()


@pytest.mark.parametrize("encoding", ["proto", "json"])
@pytest.mark.parametrize("compressed", [False, True])
def test_redacted_client_spans_on_wire(private_tracing, receiver, encoding, compressed):
    """Serialize actual client spans in both OTLP encodings (not a native-gateway test)."""
    with OpenAI(base_url=BASE_URL, api_key="tfy-test-token", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(_gateway))) as client:
        client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": PROMPT_MARK}])
        with pytest.raises(PermissionDeniedError):
            client.chat.completions.create(model="openai-main/forbidden", messages=[{"role": "user", "content": PROMPT_MARK}])
    spans = private_tracing.get_finished_spans()
    assert len(spans) == 2
    request = encode_spans(spans)
    endpoint, received = receiver
    status, _ = post_http(endpoint + "/tracer/v1/traces", request, encoding=encoding,
                          headers={}, gzip_body=compressed)
    assert status == 200 and len(received) == 1
    _, headers, raw = received[0]
    assert (headers.get("Content-Encoding") == "gzip") is compressed
    body = gzip.decompress(raw) if compressed else raw
    expected = request.SerializeToString() if encoding == "proto" else to_otlp_json(request)
    assert body == expected
    for marker in (PROMPT_MARK, ANSWER_MARK, "dev@example.test", "exception.message", "exception.stacktrace"):
        assert marker.encode() not in body
    if encoding == "json":
        rows = json.loads(body)["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(rows) == 2
        assert rows[1]["status"]["code"] == 2
        assert rows[0]["traceId"] == spans[0].context.trace_id.to_bytes(16, "big").hex()
