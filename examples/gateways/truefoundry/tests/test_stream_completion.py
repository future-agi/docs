"""The normal application must not print a partial answer as success."""

import json
from unittest.mock import Mock

import pytest
from traceai_openai import OpenAIInstrumentor

import client_example
from test_client_tracing import MODEL, httpx
from test_page_snippet import PRIVACY_FLAGS, attributes, decode_request, receiver


@pytest.mark.parametrize(
    "ending", ["eof", "done", "usage", "empty", "stop", "length", "content_filter"]
)
def test_stream_main_requires_complete_answer(monkeypatch, capsys, receiver, ending):
    endpoint, received = receiver
    for name, value in {
        "FI_BASE_URL": endpoint,
        "FI_API_KEY": "synthetic-fi-key",
        "FI_SECRET_KEY": "synthetic-fi-secret",
        "TFY_API_KEY": "synthetic-tfy-token",
        "TFY_MODEL": MODEL,
        "TFY_BASE_URL": "https://gateway.truefoundry.ai",
        "OTEL_EXPORTER_OTLP_TRACES_COMPRESSION": "none",
    }.items():
        monkeypatch.setenv(name, value)
    for flag in PRIVACY_FLAGS:
        monkeypatch.setenv(flag, "true")
    chunk = {
        "id": "synthetic-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": MODEL,
        "choices": [
            {"index": 0, "delta": {"content": "answer text"}, "finish_reason": None}
        ],
    }
    payload = "" if ending == "empty" else "data: " + json.dumps(chunk) + "\n\n"
    if ending in {"stop", "length", "content_filter"}:
        chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": ending}]
        payload += "data: " + json.dumps(chunk) + "\n\n"
    if ending in {"usage", "stop"}:
        chunk["choices"] = []
        chunk["usage"] = {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4}
        payload += "data: " + json.dumps(chunk) + "\n\n"
    if ending in {"done", "stop"}:
        payload += "data: [DONE]\n\n"
    responses = []

    def handler(request):
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=httpx.ByteStream(payload.encode()),
        )
        responses.append(response)
        return response

    class MockedOpenAI(client_example.OpenAI):
        def __init__(self, **kwargs):
            super().__init__(
                http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                max_retries=0,
                **kwargs,
            )

    original_build = client_example.build
    providers = []

    def build():
        provider, client, tracer = original_build()
        provider = Mock(wraps=provider)
        providers.append(provider)
        return provider, client, tracer

    monkeypatch.setattr(client_example, "OpenAI", MockedOpenAI)
    monkeypatch.setattr(client_example, "build", build)
    try:
        code = client_example.main(["client_example.py", "--stream", "question"])
    finally:
        OpenAIInstrumentor().uninstrument()
    output = capsys.readouterr()
    assert code == (0 if ending == "stop" else 1)
    assert output.out.strip() == ("answer text" if ending == "stop" else "")
    assert bool(output.err) == (ending != "stop")
    assert responses[0].is_closed
    (provider,) = providers
    provider.force_flush.assert_called_once_with()
    provider.shutdown.assert_called_once_with()

    (batch,) = received
    path, _, _, request = decode_request(batch)
    assert path == "/tracer/v1/traces"
    (resource,) = request.resource_spans
    (scope,) = resource.scope_spans
    (span,) = scope.spans
    assert span.name == "ChatCompletion"
    # The pinned instrumentor finishes on stream exhaustion, before the app
    # validates finish_reason. An OK span does not prove answer completeness.
    assert span.status.code == 1  # OTLP StatusCode.OK, including rejected answers
    if ending == "stop":
        assert attributes(span.attributes)["gen_ai.usage.total_tokens"] == 4


@pytest.mark.parametrize(
    "error", [RuntimeError("synthetic failure"), KeyboardInterrupt()]
)
def test_stream_cleanup_preserves_iteration_error(error):
    class InterruptedStream:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def __iter__(self):
            raise error

    stream = InterruptedStream()
    client = Mock()
    client.chat.completions.create.return_value = stream
    with pytest.raises(type(error)) as caught:
        client_example.run_stream(client, MODEL, "question")
    assert caught.value is error
    assert stream.closed
