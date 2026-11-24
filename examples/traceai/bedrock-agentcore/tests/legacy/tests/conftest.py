"""Test fixtures: in-memory exporters, a clean global tracer provider per test, a real BedrockAgentCoreApp."""

import os
import sys

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.util._once import Once

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Never reach a real Future AGI from unit tests.
os.environ.setdefault("FI_API_KEY", "unit-test-key")
os.environ.setdefault("FI_SECRET_KEY", "unit-test-secret")
os.environ.setdefault("FI_BASE_URL", "http://127.0.0.1:9")

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
CALLER_TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
CALLER_SPAN = "00f067aa0ba902b7"
TRACEPARENT = f"00-{CALLER_TRACE}-{CALLER_SPAN}-01"


def _reset_global_provider():
    # OpenTelemetry lets a process set the global provider once; tests need a fresh one each time.
    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    import bedrock_agentcore.runtime.tracing as agentcore_tracing_module

    agentcore_tracing_module._registered_on = None


@pytest.fixture(autouse=True)
def clean_global_provider():
    _reset_global_provider()
    yield
    _reset_global_provider()


@pytest.fixture
def memory_exporter():
    return InMemorySpanExporter()
