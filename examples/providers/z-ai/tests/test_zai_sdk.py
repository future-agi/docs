"""Z.ai's own SDK is not traced by traceAI-openai.

Optional: needs `pip install zai-sdk`. `ZaiClient` is not a subclass of `openai.OpenAI`, and the
instrumentor wraps `openai.OpenAI.request`, so a ZaiClient call produces no span while the stock
`openai.OpenAI` client, pointed at the same server, produces one. ZaiClient is only pointed at the
local stand-in here; nothing is sent to Z.ai."""
import pytest

zai = pytest.importorskip("zai")

from conftest import MODEL, ZAI_KEY  # noqa: E402
from fi_instrumentation import register  # noqa: E402
from fi_instrumentation.fi_types import ProjectType  # noqa: E402
from openai import OpenAI  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402
from traceai_openai import OpenAIInstrumentor  # noqa: E402


@pytest.fixture()
def traced(monkeypatch):
    monkeypatch.setenv("FI_API_KEY", "test-fi-api-key-0002")
    monkeypatch.setenv("FI_SECRET_KEY", "test-fi-secret-key-0003")
    exporter = InMemorySpanExporter()
    provider = register(
        project_type=ProjectType.OBSERVE, project_name="z-ai-sdk", batch=False, span_exporter=exporter, verbose=False
    )
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    yield exporter
    instrumentor.uninstrument()
    provider.shutdown()


def test_zaiclient_is_not_an_openai_client():
    assert not issubclass(zai.ZaiClient, OpenAI)


def test_zaiclient_defaults_to_the_same_general_platform_url():
    assert str(zai.ZaiClient(api_key="k").base_url).rstrip("/") == "https://api.z.ai/api/paas/v4"


def test_a_zaiclient_call_makes_no_span_but_the_openai_client_does(traced, plain_stub):
    reply = zai.ZaiClient(api_key=ZAI_KEY, base_url=plain_stub.url).chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": "hi"}]
    )
    assert reply.choices[0].message.content == "Z.ai stand-in reply to: hi"
    assert traced.get_finished_spans() == (), "traceAI-openai does not instrument ZaiClient"

    OpenAI(api_key=ZAI_KEY, base_url=plain_stub.url).chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": "hi"}]
    )
    (span,) = traced.get_finished_spans()
    assert dict(span.attributes)["gen_ai.request.model"] == MODEL
