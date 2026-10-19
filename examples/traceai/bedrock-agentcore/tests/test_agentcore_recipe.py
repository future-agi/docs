"""Contract tests for the AgentCore recipe, against the real bedrock-agentcore BedrockAgentCoreApp.

The app is served in-process with Starlette's TestClient: the same ASGI app `app.run()` serves on
port 8080 in the AgentCore container. Spans go to in-memory exporters; nothing leaves the machine.
"""

import asyncio
import json
import os
import time

import pytest
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from conftest import CALLER_SPAN, CALLER_TRACE, SESSION_HEADER, TRACEPARENT
from fi_instrumentation import get_attributes_from_context, register
from fi_instrumentation.fi_types import ProjectType
from opentelemetry import baggage, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from starlette.testclient import TestClient

import agentcore_tracing

MARKER = "mk-th8226-unit-7f3c"


def fi_provider(exporter, *, global_provider=True, keep=True):
    """register() as the example calls it. With keep, `exporter` is the one that stays attached.

    register()'s own processor is shut down (with its exporter) when it is replaced, so it gets a
    throwaway exporter whenever keep_future_agi_exporter() supplies the real one.
    """
    provider = register(
        project_name="agentcore-unit",
        project_type=ProjectType.OBSERVE,
        set_global_tracer_provider=global_provider,
        span_exporter=InMemorySpanExporter() if keep else exporter,
        verbose=False,
    )
    if keep:
        agentcore_tracing.keep_future_agi_exporter(provider, span_exporter=exporter)
    return provider


def make_app(provider, body=None, **traced_kwargs):
    app = BedrockAgentCoreApp()
    seen = {}

    @app.entrypoint
    def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider, **traced_kwargs):
            seen["context_attributes"] = dict(get_attributes_from_context())
            seen["baggage_session"] = baggage.get_baggage("session.id")
            with trace.get_tracer("framework").start_as_current_span("framework.step"):
                if body:
                    return body(payload)
                return {"ok": True}

    return app, seen


def call(app, headers=None, payload=None):
    return TestClient(app).post("/invocations", json=payload or {"prompt": "hi"}, headers=headers or {})


def by_name(spans):
    return {s.name: s for s in spans}


# --- the BaggageSpanProcessor hazard ------------------------------------------------------


def test_without_keep_agentcore_drops_the_future_agi_exporter(memory_exporter):
    provider = fi_provider(memory_exporter, keep=False)
    app, _ = make_app(provider)
    assert call(app).status_code == 200
    provider.force_flush()
    assert memory_exporter.get_finished_spans() == ()  # constructing the app removed the exporter


def test_keep_future_agi_exporter_survives_agentcore(memory_exporter):
    provider = fi_provider(memory_exporter)
    app, _ = make_app(provider)
    assert call(app).status_code == 200
    names = [type(p).__name__ for p in provider._active_span_processor._span_processors]
    assert names == ["BatchSpanProcessor", "BaggageSpanProcessor"]
    assert set(by_name(memory_exporter.get_finished_spans())) == {"agentcore.invocation", "framework.step"}


def test_keep_also_survives_a_provider_registered_after_the_app(memory_exporter):
    app_first = BedrockAgentCoreApp()  # registers on the no-op proxy provider
    provider = fi_provider(memory_exporter)

    @app_first.entrypoint
    def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider):
            return {"ok": True}

    assert call(app_first).status_code == 200  # first request re-registers on the new provider
    assert call(app_first).status_code == 200
    assert len(memory_exporter.get_finished_spans()) == 2


def test_register_without_global_provider_needs_no_keep(memory_exporter):
    provider = fi_provider(memory_exporter, global_provider=False, keep=False)
    app, _ = make_app(provider)
    assert call(app).status_code == 200
    assert "agentcore.invocation" in by_name(memory_exporter.get_finished_spans())


# --- session, caller trace, root span --------------------------------------------------------


def test_session_header_becomes_session_id_everywhere(memory_exporter):
    provider = fi_provider(memory_exporter)
    app, seen = make_app(provider)
    assert call(app, {SESSION_HEADER: "sess-0001"}).status_code == 200
    root = by_name(memory_exporter.get_finished_spans())["agentcore.invocation"]
    assert root.attributes["session.id"] == "sess-0001"
    assert root.attributes["fi.span.kind"] == "CHAIN"
    assert seen["context_attributes"].get("session.id") == "sess-0001"  # traceAI instrumentors read this
    assert seen["baggage_session"] == "sess-0001"  # a baggage span processor reads this


def test_no_session_header_no_session_attribute(memory_exporter):
    provider = fi_provider(memory_exporter)
    app, seen = make_app(provider)
    assert call(app).status_code == 200
    root = by_name(memory_exporter.get_finished_spans())["agentcore.invocation"]
    assert "session.id" not in root.attributes
    assert "session.id" not in seen["context_attributes"]


def test_caller_traceparent_is_linked_not_joined_by_default(memory_exporter):
    provider = fi_provider(memory_exporter)
    app, _ = make_app(provider)
    assert call(app, {"traceparent": TRACEPARENT, "baggage": "tenant=t1"}).status_code == 200
    spans = by_name(memory_exporter.get_finished_spans())
    root, child = spans["agentcore.invocation"], spans["framework.step"]
    assert root.parent is None  # Future AGI lists the trace by this parentless root
    assert format(root.context.trace_id, "032x") != CALLER_TRACE
    assert [(format(link.context.trace_id, "032x"), format(link.context.span_id, "016x")) for link in root.links] == [
        (CALLER_TRACE, CALLER_SPAN)
    ]
    assert child.parent.span_id == root.context.span_id


def test_caller_traceparent_is_joined_on_request(memory_exporter):
    provider = fi_provider(memory_exporter)
    app, _ = make_app(provider, join_caller_trace=True)
    assert call(app, {"traceparent": TRACEPARENT}).status_code == 200
    spans = by_name(memory_exporter.get_finished_spans())
    root, child = spans["agentcore.invocation"], spans["framework.step"]
    assert format(root.context.trace_id, "032x") == CALLER_TRACE
    assert format(root.parent.span_id, "016x") == CALLER_SPAN
    assert root.links == ()
    assert child.parent.span_id == root.context.span_id


def test_request_baggage_is_kept_without_joining(memory_exporter):
    provider = fi_provider(memory_exporter)
    app = BedrockAgentCoreApp()
    seen = {}

    @app.entrypoint
    def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider):
            seen.update(baggage.get_all())
            return {"ok": True}

    assert call(app, {"traceparent": TRACEPARENT, "baggage": "tenant=t1", SESSION_HEADER: "s-b"}).status_code == 200
    assert seen == {"tenant": "t1", "session.id": "s-b"}


def test_without_traceparent_each_invocation_is_a_new_trace(memory_exporter):
    provider = fi_provider(memory_exporter)
    app, _ = make_app(provider)
    for _ in range(3):
        assert call(app, {SESSION_HEADER: "sess-multi"}).status_code == 200
    roots = [s for s in memory_exporter.get_finished_spans() if s.name == "agentcore.invocation"]
    assert len(roots) == 3 and all(r.parent is None for r in roots)
    assert len({r.context.trace_id for r in roots}) == 3
    assert {r.attributes["session.id"] for r in roots} == {"sess-multi"}


def test_root_span_carries_no_payload(memory_exporter):
    provider = fi_provider(memory_exporter)
    app, _ = make_app(provider)
    assert call(app, payload={"prompt": MARKER}).status_code == 200
    assert MARKER not in json.dumps([json.loads(s.to_json()) for s in memory_exporter.get_finished_spans()])


def test_outer_context_attributes_are_kept(memory_exporter):
    from fi_instrumentation import using_user

    provider = fi_provider(memory_exporter)
    app = BedrockAgentCoreApp()
    seen = {}

    @app.entrypoint
    def invoke(payload, context):
        with using_user("user-42"):
            with agentcore_tracing.traced_invocation(context, provider):
                seen.update(get_attributes_from_context())
        return {"ok": True}

    assert call(app, {"traceparent": TRACEPARENT, SESSION_HEADER: "s-o"}).status_code == 200
    assert seen.get("user.id") == "user-42" and seen.get("session.id") == "s-o"


# --- error path and flush ----------------------------------------------------------------------


def test_error_marks_root_with_type_name_only_and_still_flushes(memory_exporter):
    provider = register(project_name="agentcore-unit", project_type=ProjectType.OBSERVE,
                        set_global_tracer_provider=True, span_exporter=InMemorySpanExporter(), verbose=False)
    # a batch processor whose timer would not fire for a minute: only the explicit flush exports
    provider.add_span_processor(BatchSpanProcessor(memory_exporter, schedule_delay_millis=60_000))

    def boom(payload):
        raise ValueError(f"cannot handle {payload['prompt']}")

    app, _ = make_app(provider, body=boom)
    response = call(app, payload={"prompt": MARKER})
    assert response.status_code == 500  # AgentCore's own error response
    root = by_name(memory_exporter.get_finished_spans())["agentcore.invocation"]
    assert root.status.status_code is StatusCode.ERROR
    assert root.status.description == "ValueError"
    assert root.events == ()
    assert MARKER not in root.to_json()


def test_spans_are_flushed_before_the_response(memory_exporter):
    provider = register(project_name="agentcore-unit", project_type=ProjectType.OBSERVE,
                        set_global_tracer_provider=True, span_exporter=InMemorySpanExporter(), verbose=False)
    provider.add_span_processor(BatchSpanProcessor(memory_exporter, schedule_delay_millis=60_000))
    app, _ = make_app(provider)
    assert call(app).status_code == 200
    assert len(memory_exporter.get_finished_spans()) == 2  # no sleep, no shutdown: the flush exported them


def test_flush_failure_never_fails_the_invocation():
    class BrokenProvider(TracerProvider):
        def force_flush(self, timeout_millis=30000):
            raise RuntimeError("exporter exploded")

    provider = BrokenProvider()
    app, _ = make_app(provider)
    assert call(app).status_code == 200
    assert agentcore_tracing.flush(None) is False


def test_unreachable_collector_does_not_fail_and_is_bounded(monkeypatch):
    monkeypatch.setenv("FI_BASE_URL", "http://127.0.0.1:9")  # nothing listens on the discard port
    provider = register(project_name="agentcore-unit", project_type=ProjectType.OBSERVE,
                        set_global_tracer_provider=True, verbose=False)
    agentcore_tracing.keep_future_agi_exporter(provider)
    app, _ = make_app(provider, flush_timeout_millis=1000)
    started = time.monotonic()
    assert call(app).status_code == 200
    assert time.monotonic() - started < 15


def test_async_entrypoint(memory_exporter):
    provider = fi_provider(memory_exporter)
    app = BedrockAgentCoreApp()

    @app.entrypoint
    async def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider, join_caller_trace=True):
            await asyncio.sleep(0)
            with trace.get_tracer("framework").start_as_current_span("framework.async"):
                return {"ok": True}

    assert call(app, {SESSION_HEADER: "sess-async", "traceparent": TRACEPARENT}).status_code == 200
    spans = by_name(memory_exporter.get_finished_spans())
    assert spans["framework.async"].parent.span_id == spans["agentcore.invocation"].context.span_id
    assert format(spans["agentcore.invocation"].context.trace_id, "032x") == CALLER_TRACE


def _chunks(n, fail_at=None):
    for i in range(n):
        if i == fail_at:
            raise RuntimeError(f"stream broke at {MARKER}")
        with trace.get_tracer("framework").start_as_current_span(f"chunk.{i}"):
            yield {"chunk": i}


def _assert_stream_shape(spans, n):
    root = by_name(spans)["agentcore.invocation"]
    chunks = [s for s in spans if s.name.startswith("chunk.")]
    assert len(chunks) == n
    assert all(c.parent.span_id == root.context.span_id for c in chunks)
    assert root.end_time >= max(c.end_time for c in chunks)
    return root


def test_sync_streaming_entrypoint_with_traced_stream(memory_exporter):
    provider = fi_provider(memory_exporter)
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context):
        return agentcore_tracing.traced_stream(context, _chunks(3), provider, join_caller_trace=True)

    response = call(app, {SESSION_HEADER: "sess-stream", "traceparent": TRACEPARENT})
    assert response.status_code == 200 and response.text.count("data:") == 3
    root = _assert_stream_shape(memory_exporter.get_finished_spans(), 3)
    assert root.attributes["session.id"] == "sess-stream"
    assert format(root.context.trace_id, "032x") == CALLER_TRACE


def test_sync_streaming_error_marks_root(memory_exporter):
    provider = fi_provider(memory_exporter)
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context):
        return agentcore_tracing.traced_stream(context, _chunks(3, fail_at=2), provider)

    response = call(app)
    assert response.status_code == 200 and '"error_type": "RuntimeError"' in response.text  # AgentCore's SSE error event
    root = _assert_stream_shape(memory_exporter.get_finished_spans(), 2)
    assert root.status.status_code is StatusCode.ERROR and root.status.description == "RuntimeError"


def test_sync_generator_with_context_manager_loses_the_parent(memory_exporter):
    """Why traced_stream exists: with the context manager, chunks are not children of the root."""
    provider = fi_provider(memory_exporter)
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider):
            yield from _chunks(3)

    assert call(app).status_code == 200
    chunks = [s for s in memory_exporter.get_finished_spans() if s.name.startswith("chunk.")]
    assert any(c.parent is None for c in chunks)


def test_async_generator_entrypoint_with_traced_invocation(memory_exporter):
    provider = fi_provider(memory_exporter)
    app = BedrockAgentCoreApp()

    @app.entrypoint
    async def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider):
            for i in range(3):
                await asyncio.sleep(0)
                with trace.get_tracer("framework").start_as_current_span(f"chunk.{i}"):
                    yield {"chunk": i}

    response = call(app, {SESSION_HEADER: "sess-astream"})
    assert response.status_code == 200 and response.text.count("data:") == 3
    root = _assert_stream_shape(memory_exporter.get_finished_spans(), 3)
    assert root.attributes["session.id"] == "sess-astream"


# --- traceAI LangChain instrumentor inside the entrypoint -------------------------------------


def test_traceai_langchain_spans_get_the_agentcore_session(memory_exporter):
    from langchain_core.runnables import RunnableLambda
    from traceai_langchain import LangChainInstrumentor

    provider = fi_provider(memory_exporter)
    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        chain = RunnableLambda(lambda x: x.upper()).with_config(run_name="upper_chain")
        app = BedrockAgentCoreApp()

        @app.entrypoint
        def invoke(payload, context):
            with agentcore_tracing.traced_invocation(context, provider, join_caller_trace=True):
                return {"result": chain.invoke(payload["prompt"])}

        assert call(app, {SESSION_HEADER: "sess-lc", "traceparent": TRACEPARENT}).status_code == 200
    finally:
        instrumentor.uninstrument()
    spans = by_name(memory_exporter.get_finished_spans())
    lc = spans["upper_chain"]
    assert lc.attributes.get("session.id") == "sess-lc"
    assert lc.parent.span_id == spans["agentcore.invocation"].context.span_id
    assert format(lc.context.trace_id, "032x") == CALLER_TRACE


# --- error text of traceAI LangChain spans (keep_future_agi_exporter wraps ErrorTextExporter) ----

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _failing_langchain_app(provider, config=None):
    """A LangChain chain that fails inside an AgentCore entrypoint, traced by the real traceAI-langchain."""
    from langchain_core.runnables import RunnableLambda
    from traceai_langchain import LangChainInstrumentor

    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(tracer_provider=provider, **({"config": config} if config else {}))

    def lookup(order_id):
        raise ValueError(f"no order {order_id}")

    chain = (RunnableLambda(lambda x: x.strip()) | RunnableLambda(lookup).with_config(run_name="lookup")).with_config(
        run_name="order_chain"
    )
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider):
            return {"result": chain.invoke(payload["prompt"])}

    return app, instrumentor


def _run_failing_langchain(provider, exporter, config=None):
    app, instrumentor = _failing_langchain_app(provider, config)
    try:
        assert call(app, {SESSION_HEADER: "sess-err"}, {"prompt": f" {MARKER} "}).status_code == 500
    finally:
        instrumentor.uninstrument()
    provider.force_flush()
    spans = by_name(exporter.get_finished_spans())
    assert {"agentcore.invocation", "order_chain", "lookup"} <= set(spans)
    return spans


def _lc_error_spans(spans):
    return [s for name, s in spans.items() if name != "agentcore.invocation" and s.status.status_code is StatusCode.ERROR]


def test_traceai_langchain_0_2_0_puts_the_traceback_in_the_status(memory_exporter, monkeypatch):
    """The package bug the wrapper works around (traceAI-langchain 0.2.0; fix proposed in traceAI#214).

    Without keep_future_agi_exporter, and with FI_HIDE_INPUTS/FI_HIDE_OUTPUTS on, the failing
    LangChain spans carry LangChain's run.error: repr(error), then the formatted traceback with
    this file's path. If this test fails after a traceAI-langchain upgrade, the release fixed the
    bug: update the note on the docs page (the wrapper stays harmless).
    """
    monkeypatch.setenv("FI_HIDE_INPUTS", "true")
    monkeypatch.setenv("FI_HIDE_OUTPUTS", "true")
    provider = fi_provider(memory_exporter, global_provider=False, keep=False)
    errors = _lc_error_spans(_run_failing_langchain(provider, memory_exporter))
    assert errors and all("Traceback (most recent call last)" in s.status.description for s in errors)
    assert any(THIS_DIR in s.status.description for s in errors)


@pytest.mark.parametrize("how", ["env", "config"])
def test_keep_exporter_reduces_langchain_errors_to_the_type_when_content_is_hidden(memory_exporter, monkeypatch, how):
    from fi_instrumentation import TraceConfig

    config = None
    if how == "env":
        monkeypatch.setenv("FI_HIDE_INPUTS", "true")
        monkeypatch.setenv("FI_HIDE_OUTPUTS", "true")
    else:
        config = TraceConfig(hide_inputs=True, hide_outputs=True)
    provider = register(project_name="agentcore-unit", project_type=ProjectType.OBSERVE,
                        set_global_tracer_provider=True, span_exporter=InMemorySpanExporter(), verbose=False)
    agentcore_tracing.keep_future_agi_exporter(provider, span_exporter=memory_exporter, config=config)
    spans = _run_failing_langchain(provider, memory_exporter, config)
    errors = _lc_error_spans(spans)
    assert {s.name for s in errors} >= {"order_chain", "lookup"}
    for span in errors:
        assert span.status.description == "ValueError"
        assert [dict(e.attributes) for e in span.events if e.name == "exception"] == [{"exception.type": "ValueError"}]
    assert spans["agentcore.invocation"].status.description == "ValueError"
    dumped = json.dumps([json.loads(s.to_json()) for s in spans.values()])
    assert MARKER not in dumped and "Traceback" not in dumped and THIS_DIR not in dumped


def test_keep_exporter_never_exports_a_langchain_traceback_with_content_on(memory_exporter):
    provider = fi_provider(memory_exporter)
    spans = _run_failing_langchain(provider, memory_exporter)
    errors = _lc_error_spans(spans)
    assert {s.name for s in errors} >= {"order_chain", "lookup"}
    for span in errors:
        assert span.status.description == f"ValueError('no order {MARKER}')"  # message kept: content is on
        for event in (e for e in span.events if e.name == "exception"):
            assert "exception.stacktrace" not in event.attributes
            assert event.attributes["exception.message"] == f"no order {MARKER}"
    dumped = json.dumps([json.loads(s.to_json()) for s in spans.values()])
    assert MARKER in dumped  # content on: the prompt is captured
    assert "Traceback" not in dumped and THIS_DIR not in dumped


@pytest.mark.parametrize(
    "env,expected",
    [
        ({}, False),
        ({"FI_HIDE_INPUTS": "true"}, True),
        ({"FI_HIDE_OUTPUTS": "true"}, True),
        ({"FI_HIDE_INPUT_MESSAGES": "true"}, True),
        ({"FI_HIDE_OUTPUT_MESSAGES": "true"}, True),
        ({"FI_HIDE_INPUT_TEXT": "true"}, True),
        ({"FI_HIDE_OUTPUT_TEXT": "true"}, True),
        ({"FI_HIDE_LLM_INVOCATION_PARAMETERS": "true"}, False),
        ({"FI_HIDE_INPUTS": "false", "FI_HIDE_OUTPUTS": "false"}, False),
    ],
)
def test_content_hidden_follows_the_fi_hide_variables(monkeypatch, env, expected):
    for name in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_INPUT_MESSAGES", "FI_HIDE_OUTPUT_MESSAGES",
                 "FI_HIDE_INPUT_TEXT", "FI_HIDE_OUTPUT_TEXT", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert agentcore_tracing.content_hidden() is expected


def test_content_hidden_with_an_explicit_config():
    from fi_instrumentation import TraceConfig

    assert agentcore_tracing.content_hidden(TraceConfig(hide_output_messages=True)) is True
    assert agentcore_tracing.content_hidden(TraceConfig(hide_inputs=False, hide_outputs=False)) is False


# --- ErrorTextExporter / ErrorTypeOnlyExporter (both paths) --------------------------------------


def _error_span(exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(agentcore_tracing.ErrorTypeOnlyExporter(exporter)))
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("ok_span", attributes={"keep": "yes"}):
        pass
    span = tracer.start_span("failing_span")
    try:
        raise PermissionError(f"tool failed for {MARKER} at /home/someone/app.py")
    except PermissionError as exc:
        span.set_status(StatusCode.ERROR, str(exc))
        span.record_exception(exc)
    span.end()
    plain = tracer.start_span("error_without_event")
    plain.set_status(StatusCode.ERROR, f"model said no to {MARKER}")
    plain.end()
    return by_name(exporter.get_finished_spans())


def test_error_type_only_exporter_strips_message_and_stack(memory_exporter):
    spans = _error_span(memory_exporter)
    failing = spans["failing_span"]
    assert failing.status.status_code is StatusCode.ERROR
    assert failing.status.description == "PermissionError"
    assert [dict(e.attributes) for e in failing.events] == [{"exception.type": "PermissionError"}]
    assert spans["error_without_event"].status.description == "Error"
    dumped = json.dumps([json.loads(s.to_json()) for s in spans.values()])
    assert MARKER not in dumped and "Traceback" not in dumped and "/home/" not in dumped


def test_error_type_only_exporter_keeps_the_recipe_root_status(memory_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(agentcore_tracing.ErrorTypeOnlyExporter(memory_exporter)))
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context):
        with agentcore_tracing.traced_invocation(context, provider):
            raise TimeoutError("model timed out")

    assert call(app).status_code == 500
    root = by_name(memory_exporter.get_finished_spans())["agentcore.invocation"]
    assert root.status.description == "TimeoutError"


def test_error_type_only_exporter_leaves_ok_spans_alone(memory_exporter):
    spans = _error_span(memory_exporter)
    ok = spans["ok_span"]
    assert ok.attributes["keep"] == "yes" and ok.status.status_code is not StatusCode.ERROR


def _traceback_span_without_event(exporter, type_only):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(agentcore_tracing.ErrorTextExporter(exporter, type_only=type_only)))
    span = provider.get_tracer("t").start_span("chain_without_event")
    span.set_status(StatusCode.ERROR, f"KeyError('{MARKER}')Traceback (most recent call last):\n  File \"/home/someone/app.py\"")
    span.end()
    return by_name(exporter.get_finished_spans())["chain_without_event"]


def test_error_text_exporter_type_only_reads_the_type_from_a_repr_description(memory_exporter):
    span = _traceback_span_without_event(memory_exporter, type_only=True)
    assert span.status.description == "KeyError"


def test_error_text_exporter_content_on_cuts_the_traceback(memory_exporter):
    span = _traceback_span_without_event(memory_exporter, type_only=False)
    assert span.status.description == f"KeyError('{MARKER}')"


def test_error_text_exporter_content_on_keeps_message_drops_stack(memory_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(agentcore_tracing.ErrorTextExporter(memory_exporter, type_only=False)))
    span = provider.get_tracer("t").start_span("failing_span")
    try:
        raise PermissionError(f"tool failed for {MARKER}")
    except PermissionError as exc:
        span.set_status(StatusCode.ERROR, str(exc))
        span.record_exception(exc)
    span.end()
    failing = by_name(memory_exporter.get_finished_spans())["failing_span"]
    assert failing.status.description == f"tool failed for {MARKER}"
    (event,) = failing.events
    assert dict(event.attributes) == {
        "exception.type": "PermissionError",
        "exception.message": f"tool failed for {MARKER}",
        "exception.escaped": "False",
    }
    assert "Traceback" not in failing.to_json() and THIS_DIR not in failing.to_json()


def test_error_text_exporter_caps_the_message(memory_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(agentcore_tracing.ErrorTextExporter(memory_exporter, type_only=False)))
    span = provider.get_tracer("t").start_span("long_error")
    span.set_status(StatusCode.ERROR, "x" * 5000)
    span.end()
    assert len(by_name(memory_exporter.get_finished_spans())["long_error"].status.description) == agentcore_tracing.ERROR_TEXT_LIMIT


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", False),
        ("gen_ai_latest_experimental,gen_ai_span_attributes_only", False),
        ("gen_ai_latest_experimental,gen_ai_span_attributes_only,gen_ai_unredacted_attributes=", True),
        ("gen_ai_unredacted_attributes=gen_ai.output.*", True),
    ],
)
def test_strands_redaction_switch(monkeypatch, value, expected):
    monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", value)
    assert agentcore_tracing.strands_redaction_enabled() is expected
