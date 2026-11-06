"""The 1.x leg of the matrix (tested: agentscope 1.0.21, the last 1.x release).

1.x has no middleware and no way to pass headers or a resource: agentscope.init(tracing_url=...)
builds its own exporter and provider. The standard OpenTelemetry environment variables are
what carry the Future AGI keys and the project name. Run in an environment with
agentscope 1.x installed (see README); these tests are skipped on 2.x."""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import FI_API_KEY, FI_SECRET_KEY, MARKER, MODEL_KEY, ROOT, by_name

APP = ROOT / "legacy_1x" / "app_1x.py"


def run_1x(model, collector, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OPENAI", "OTEL_"))}
    clean.update(
        {
            "OPENAI_API_KEY": MODEL_KEY,
            "OPENAI_BASE_URL": model.url,
            "OPENAI_MODEL": "fake-model",
            "FI_BASE_URL": collector.url,
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS": f"X-Api-Key={FI_API_KEY},X-Secret-Key={FI_SECRET_KEY}",
            "OTEL_RESOURCE_ATTRIBUTES": "project_name=agentscope-1x-test,project_type=observe",
            "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3",
            "PROMPT": f"hello {MARKER}",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    clean.update(env or {})
    return subprocess.run([sys.executable, str(APP)], cwd=ROOT, env=clean, capture_output=True, text=True, timeout=120)


def test_env_vars_carry_keys_and_project_name(model, collector):
    model.tool_arg = f"Paris-{MARKER}"
    out = run_1x(model, collector)
    assert out.returncode == 0, out.stderr[-1500:]
    assert "RESULT chat ok" in out.stdout
    assert collector.exports
    for export in collector.exports:
        assert export["path"] == "/tracer/v1/traces"
        assert export["headers"]["x-api-key"] == FI_API_KEY and export["headers"]["x-secret-key"] == FI_SECRET_KEY
        assert export["headers"].get("content-encoding") in (None, "identity")
    spans = collector.spans()
    assert {s["_resource"]["project_name"] for s in spans} == {"agentscope-1x-test"}
    assert len({s["trace_id"] for s in spans}) == 1

    agent = by_name(spans, "invoke_agent")
    chats = by_name(spans, "chat ")
    tools = by_name(spans, "execute_tool")
    assert [len(agent), len(chats), len(tools)] == [1, 2, 1]
    for child in chats + tools:
        assert child["parent_span_id"], "children hang under a parent"
    assert all(c["_attrs"]["gen_ai.usage.input_tokens"] == 31 for c in chats)
    # 1.x also emits a span per formatter call
    assert by_name(spans, "format ")


def test_tracing_url_alone_is_not_enough(model, collector):
    """Without the environment variables 1.x sends no key headers and no project_name, which
    Future AGI rejects. This is why the page tells 1.x users to set them."""
    out = run_1x(
        model,
        collector,
        env={"OTEL_EXPORTER_OTLP_TRACES_HEADERS": "", "OTEL_RESOURCE_ATTRIBUTES": ""},
    )
    assert out.returncode == 0, out.stderr[-1500:]
    assert collector.exports
    assert all("x-api-key" not in e["headers"] for e in collector.exports)
    assert all("project_name" not in s["_resource"] for s in collector.spans())


def test_1x_has_no_content_switch(model, collector):
    """1.x exports prompts, answers and tool payloads whatever you set. Pinned so that the
    page's statement stays true."""
    model.tool_arg = f"Paris-{MARKER}"
    out = run_1x(model, collector, env={"FI_CAPTURE_CONTENT": "0", "OTEL_SDK_DISABLED": "false"})
    assert out.returncode == 0, out.stderr[-1500:]
    assert MARKER in collector.everything()
