"""The fixture check for the documented base URL: the real `openai` client built with the exact
string from the docs page, the real instrumentor, and no network. Nothing here calls api.z.ai.

Asserts what the architecture asks of the TH-8339-style fixture: the base URL, the model, the
project_name and the provider label."""
import asyncio

import pytest
import zai_stub
from conftest import MODEL, ZAI_KEY, ZAI_URL, httpx
from fi_instrumentation import register
from fi_instrumentation.fi_types import ProjectType
from openai import AsyncOpenAI, OpenAI
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from traceai_openai import OpenAIInstrumentor


@pytest.fixture()
def traced(monkeypatch):
    monkeypatch.setenv("FI_API_KEY", "test-fi-api-key-0002")
    monkeypatch.setenv("FI_SECRET_KEY", "test-fi-secret-key-0003")
    exporter = InMemorySpanExporter()
    provider = register(
        project_type=ProjectType.OBSERVE,
        project_name="z-ai-fixture",
        batch=False,
        span_exporter=exporter,
        verbose=False,
    )
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    yield exporter
    instrumentor.uninstrument()
    provider.shutdown()


def handler(seen):
    stub = zai_stub.Stub(ZAI_KEY)

    def _handle(request):
        import json

        seen.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json=zai_stub.build_response(stub, body, 1))

    return _handle


def test_documented_base_url_model_project_and_provider(traced):
    seen = []
    client = OpenAI(
        api_key=ZAI_KEY,
        base_url="https://api.z.ai/api/paas/v4/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler(seen))),
    )
    reply = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "What is the capital of France?"}])
    assert reply.choices[0].message.content == "Z.ai stand-in reply to: What is the capital of France?"

    # the request the client built from the documented string
    (request,) = seen
    assert str(request.url) == "https://api.z.ai/api/paas/v4/chat/completions"
    assert request.method == "POST"
    assert request.headers["authorization"] == f"Bearer {ZAI_KEY}"
    assert str(client.base_url) == ZAI_URL
    assert client.base_url.host == "api.z.ai"

    (span,) = traced.get_finished_spans()
    attrs = dict(span.attributes)
    assert attrs["gen_ai.request.model"] == MODEL
    assert attrs["gen_ai.provider.name"] == "openai"
    assert attrs["gen_ai.span.kind"] == "LLM"
    assert span.resource.attributes["project_name"] == "z-ai-fixture"
    # the host is not recorded anywhere on the span or its resource
    assert "z.ai" not in repr(attrs) and "z.ai" not in repr(dict(span.resource.attributes))


def test_the_url_without_the_trailing_slash_reaches_the_same_path(traced):
    seen = []
    client = OpenAI(
        api_key=ZAI_KEY,
        base_url="https://api.z.ai/api/paas/v4",
        http_client=httpx.Client(transport=httpx.MockTransport(handler(seen))),
    )
    client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "hi"}])
    assert str(seen[0].url) == "https://api.z.ai/api/paas/v4/chat/completions"


def test_the_async_client_is_traced_the_same_way(traced):
    seen = []

    async def go():
        client = AsyncOpenAI(
            api_key=ZAI_KEY,
            base_url="https://api.z.ai/api/paas/v4/",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler(seen))),
        )
        return await client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "hi"}])

    asyncio.run(go())
    assert str(seen[0].url) == "https://api.z.ai/api/paas/v4/chat/completions"
    (span,) = traced.get_finished_spans()
    assert dict(span.attributes)["gen_ai.request.model"] == MODEL
    assert dict(span.attributes)["gen_ai.provider.name"] == "openai"


def test_a_coding_plan_base_url_would_be_traced_too_which_is_why_the_page_warns(traced):
    """The instrumentor wraps OpenAI.request, so it cannot tell the products apart. This is the reason
    the page names the three Coding Plan URLs: tracing would work, and the bill would differ."""
    seen = []
    client = OpenAI(
        api_key=ZAI_KEY,
        base_url="https://api.z.ai/api/coding/paas/v4",
        http_client=httpx.Client(transport=httpx.MockTransport(handler(seen))),
    )
    client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "hi"}])
    assert str(seen[0].url) == "https://api.z.ai/api/coding/paas/v4/chat/completions"
    (span,) = traced.get_finished_spans()
    assert dict(span.attributes)["gen_ai.provider.name"] == "openai"
