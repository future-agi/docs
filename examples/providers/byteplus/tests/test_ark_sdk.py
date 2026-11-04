"""Optional: BytePlus's own SDK (`pip install arkruntime`) is not covered by traceAI-openai.

The docs page says so. Skipped when arkruntime is not installed."""
import pytest

arkruntime = pytest.importorskip("arkruntime")


def test_ark_client_is_not_an_openai_client_and_produces_no_spans(stub):
    import openai
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from traceai_openai import OpenAIInstrumentor

    from conftest import ARK_KEY

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        ark = arkruntime.Ark(api_key=ARK_KEY, base_url=stub.url)
        assert not isinstance(ark, openai.OpenAI)
        reply = ark.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}])
        assert reply.choices[0].message.content == "echo: hi"
        assert exporter.get_finished_spans() == ()

        # the same instrumentor does trace the stock client against the same server
        openai.OpenAI(api_key=ARK_KEY, base_url=stub.url).chat.completions.create(
            model="m", messages=[{"role": "user", "content": "hi"}]
        )
        assert len(exporter.get_finished_spans()) == 1
    finally:
        instrumentor.uninstrument()
