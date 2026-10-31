"""Pins the restate-sdk behaviour the page relies on, and the example's own spans.

restate.ext.tracing.RestateTracer parents every span under the traceparent Restate sends with
the attempt, and returns a non-recording span while the SDK replays journaled steps.
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import agent_service
import pytest
from fi_instrumentation import FITracer, TraceConfig
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from restate.ext.tracing import RestateTracerProvider, _tracing
from restate.server_context import restate_context_is_replaying

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
ATTEMPT_SPAN = "00f067aa0ba902b7"


class _Request:
    attempt_headers = {"traceparent": f"00-{TRACE_ID}-{ATTEMPT_SPAN}-01"}


class _Ctx:
    def request(self):
        return _Request()


@pytest.fixture
def traced(monkeypatch):
    """An in-memory provider wrapped exactly as agent_service.py wraps the Future AGI one."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(_tracing, "current_context", lambda: _Ctx())
    monkeypatch.setattr(_tracing, "get_extension_data", lambda ctx, key: None)
    monkeypatch.setattr(_tracing, "set_extension_data", lambda ctx, key, value: None)
    return RestateTracerProvider(provider), exporter


def test_spans_join_the_restate_attempt_span(traced):
    provider, exporter = traced
    tracer = FITracer(provider.get_tracer("t"), config=TraceConfig())
    with tracer.start_as_current_span("outer", fi_span_kind="chain"):
        with tracer.start_as_current_span("inner", fi_span_kind="tool"):
            pass
    spans = {s.name: s for s in exporter.get_finished_spans()}
    for s in spans.values():  # flattened: both are children of the attempt span
        assert format(s.context.trace_id, "032x") == TRACE_ID
        assert format(s.parent.span_id, "016x") == ATTEMPT_SPAN


def test_no_span_while_replaying(traced):
    provider, exporter = traced
    tracer = FITracer(provider.get_tracer("t"), config=TraceConfig())
    token = restate_context_is_replaying.set(True)
    try:
        with tracer.start_as_current_span("replayed", fi_span_kind="llm") as span:
            assert not span.is_recording()
    finally:
        restate_context_is_replaying.reset(token)
    assert exporter.get_finished_spans() == ()


@pytest.fixture
def service_tracer(traced, monkeypatch):
    provider, exporter = traced

    def use(config: TraceConfig):
        monkeypatch.setattr(agent_service, "tracer", FITracer(provider.get_tracer("t"), config=config))
        monkeypatch.setattr(agent_service, "_failed_once", set())
        return exporter

    return use


def test_tool_span_records_arguments_and_result(service_tracer):
    exporter = service_tracer(TraceConfig())
    out = asyncio.run(agent_service.get_weather("inv_1", json.dumps({"city": "Lisbon"}), flaky=False))
    (span,) = exporter.get_finished_spans()
    assert out == "Lisbon: 21C and sunny"
    assert span.attributes["gen_ai.span.kind"] == "TOOL"
    assert span.attributes["gen_ai.tool.name"] == "get_weather"
    assert "Lisbon" in span.attributes["input.value"] and span.attributes["output.value"] == out


def test_failed_tool_span_keeps_the_error_type_only(service_tracer):
    exporter = service_tracer(TraceConfig())
    with pytest.raises(TimeoutError):
        asyncio.run(agent_service.get_weather("inv_2", json.dumps({"city": "Lisbon"}), flaky=True))
    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "TimeoutError"
    assert span.events == ()  # no exception event, so no message text and no stack trace
    # the retry of the same invocation succeeds
    asyncio.run(agent_service.get_weather("inv_2", json.dumps({"city": "Lisbon"}), flaky=True))
    assert exporter.get_finished_spans()[-1].status.status_code is not StatusCode.ERROR


def test_hide_switches_keep_tool_content_out(service_tracer):
    exporter = service_tracer(TraceConfig(hide_inputs=True, hide_outputs=True))
    asyncio.run(agent_service.get_weather("inv_3", json.dumps({"city": "Zqmarkerville"}), flaky=False))
    (span,) = exporter.get_finished_spans()
    assert "Zqmarkerville" not in json.dumps(dict(span.attributes))
    assert span.attributes["gen_ai.tool.name"] == "get_weather"


def test_script_entry_uses_standard_supervisor_and_exits_on_sigterm(tmp_path):
    """The documented entry point remains a single command and exits through Hypercorn's supervisor."""
    log = tmp_path / "service.log"
    env = {"FI_API_KEY": "a", "FI_SECRET_KEY": "b", "FI_BASE_URL": "http://127.0.0.1:1", "OPENAI_API_KEY": "c",
           "SERVICE_PORT": "19899", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    script = Path(agent_service.__file__)
    with open(log, "w") as f:
        proc = subprocess.Popen([sys.executable, str(script)], env=env, stdout=f, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 30
        while "Running on" not in log.read_text() and time.time() < deadline:
            time.sleep(0.2)
        assert "Running on" in log.read_text()
        proc.terminate()
        assert proc.wait(timeout=20) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
