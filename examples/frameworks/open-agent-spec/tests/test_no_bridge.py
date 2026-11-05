"""PRD spike gate (J0 / R-02), kept as a regression test.

pyagentspec's tracing package is a span bus with no OpenTelemetry code. With a global
tracer provider and no instrumentor, the LangGraph adapter exports nothing to
OpenTelemetry, while the bus carries the Agent Spec span tree. The adapter also leaves the
token counts of ``LlmGenerationResponse`` empty. If a pyagentspec release changes either
fact, this test fails and the page needs a look.
"""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import pyagentspec

from fake_openai import FakeOpenAI

PROBE = Path(__file__).resolve().parent / "no_bridge_probe.py"


def test_pyagentspec_has_no_opentelemetry_code():
    root = Path(pyagentspec.__file__).parent
    hits = [p for p in root.rglob("*.py") if "import opentelemetry" in p.read_text(encoding="utf-8")
            or "from opentelemetry" in p.read_text(encoding="utf-8")]
    assert hits == [], hits


def test_adapter_emits_on_the_bus_only():
    with FakeOpenAI("probe-key") as fake:
        out = subprocess.run([sys.executable, str(PROBE), fake.url, "probe-key"],
                             capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["otel"] == [], "spans reached OpenTelemetry without an instrumentor"
    names = [s["name"] for s in result["bus"]]
    assert names == [
        "LlmGenerationSpan",
        "ToolExecution[get_weather]",
        "LlmGenerationSpan",
        "AgentExecution[weather_assistant]",
        "RootSpan",
    ], names
    tokens = [t for s in result["bus"] for t in s["tokens"]]
    assert tokens == [[None, None], [None, None]], "the LangGraph adapter now reports tokens"


def test_tested_versions():
    assert importlib.metadata.version("pyagentspec") == "26.3.1"
    assert importlib.metadata.version("traceai-langchain") == "0.2.1"
    assert importlib.metadata.version("fi-instrumentation-otel") == "1.2.2"
