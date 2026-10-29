"""The client snippet on the docs page runs as written.

The page's first Python block is executed with three substitutions, nothing else: register() is
replaced by a provider that keeps spans in memory (the real one calls Future AGI), and the OpenAI
client gets a mock transport that answers at https://gateway.truefoundry.ai. If the page and the
installed packages drift apart, this fails.
"""
import json
import os
import re

import pytest

try:
    import httpx2 as httpx
except ImportError:
    import httpx

import fi_instrumentation
import openai
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

PAGE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "src", "pages", "docs",
    "integrations", "gateways", "truefoundry.mdx",
)


def test_page_client_snippet_runs(monkeypatch, capsys):
    if not os.path.exists(PAGE):
        pytest.skip("docs page not in this checkout")
    snippet = next(b for b in re.findall(r"```python\n(.*?)\n```", open(PAGE).read(), re.S) if "register(" in b)

    exporter = InMemorySpanExporter()
    registered = {}

    def fake_register(**kwargs):
        registered.update(kwargs)
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return provider

    def gateway(request):
        assert request.url == "https://gateway.truefoundry.ai/chat/completions"
        assert json.loads(request.content)["model"] == "openai-main/gpt-4o-mini"
        return httpx.Response(
            200,
            json={
                "id": "c1", "object": "chat.completion", "created": 1, "model": "gpt-4o-mini-2024-07-18",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Paris"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 14, "completion_tokens": 1, "total_tokens": 15},
            },
        )

    real_openai = openai.OpenAI

    class MockedOpenAI(real_openai):
        def __init__(self, **kwargs):
            super().__init__(http_client=httpx.Client(transport=httpx.MockTransport(gateway)), **kwargs)

    monkeypatch.setenv("TFY_API_KEY", "tfy-test-token")
    monkeypatch.setattr(fi_instrumentation, "register", fake_register)
    monkeypatch.setattr(openai, "OpenAI", MockedOpenAI)
    namespace = {"__name__": "page_snippet"}
    try:
        exec(compile(snippet, "truefoundry.mdx", "exec"), namespace)  # noqa: S102
    finally:
        namespace["OpenAIInstrumentor"]().uninstrument()

    assert capsys.readouterr().out.strip() == "Paris"
    assert registered["project_name"] == "my-chatbot" and registered["project_type"].value == "observe"
    (span,) = exporter.get_finished_spans()
    assert span.name == "ChatCompletion" and span.attributes["gen_ai.usage.total_tokens"] == 15
