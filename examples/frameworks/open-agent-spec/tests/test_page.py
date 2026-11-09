"""Run the page's maintained setup as written against loopback model and OTLP servers."""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import kind
from fake_openai import FakeOpenAI
from otlp_recorder import Recorder

EXAMPLE = Path(__file__).resolve().parent.parent
PAGE = EXAMPLE.parents[2] / "src" / "pages" / "docs" / "integrations" / "frameworks" / "open-agent-spec.mdx"
pytestmark = pytest.mark.skipif(not PAGE.exists(), reason="docs page not next to the example")


def block(title: str) -> str:
    text = PAGE.read_text(encoding="utf-8")
    match = re.search(r'```python title="' + re.escape(title) + r'"\n(.*?)```', text, re.S)
    assert match, f"no code block titled {title}"
    return match.group(1)


def test_self_hosted_origin_is_set_explicitly():
    text = PAGE.read_text(encoding="utf-8")
    assert '\nexport FI_BASE_URL="http://localhost:4318"' in text
    assert '# export FI_BASE_URL=' not in text


@pytest.mark.parametrize("hide_content", [False, True])
def test_app_on_the_page_runs_as_written(tmp_path, hide_content):
    (tmp_path / "app.py").write_text(block("app.py"), encoding="utf-8")
    key = "model-key-" + secrets.token_hex(8)
    with Recorder() as recorder, FakeOpenAI(key) as fake:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OTEL_", "MODEL_"))}
        env.update(FI_API_KEY="fi-a", FI_SECRET_KEY="fi-b", FI_BASE_URL=recorder.origin,
                   FI_PROJECT_NAME="oas-page", MODEL_BASE_URL=fake.url, MODEL_API_KEY=key,
                   MODEL_ID="fake-model", FI_HIDE_INPUTS=str(hide_content).lower(),
                   FI_HIDE_OUTPUTS=str(hide_content).lower())
        out = subprocess.run([sys.executable, "-I", str(tmp_path / "app.py")], env=env,
                             capture_output=True, text=True, timeout=180)
        spans = recorder.spans()
        raw = recorder.raw()
    assert out.returncode == 0, out.stderr[-2000:]
    assert "It is sunny" in out.stdout
    assert [s["name"] for s in spans if not s["parentSpanId"]] == ["weather_assistant"]
    assert sorted(kind(s) for s in spans) == ["CHAIN"] * 4 + ["LLM"] * 2 + ["TOOL"]
    assert {s["resource"]["project_name"] for s in spans} == {"oas-page"}
    assert key.encode() not in raw
    assert (b"What is the weather in Lisbon?" in raw) is not hide_content


def test_app_on_the_page_flushes_on_failure(tmp_path):
    (tmp_path / "app.py").write_text(block("app.py"), encoding="utf-8")
    with Recorder() as recorder, FakeOpenAI("expected-key") as fake:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OTEL_", "MODEL_"))}
        env.update(FI_API_KEY="fi-a", FI_SECRET_KEY="fi-b", FI_BASE_URL=recorder.origin,
                   FI_PROJECT_NAME="oas-page", MODEL_BASE_URL=fake.url,
                   MODEL_API_KEY="wrong-synthetic-key", MODEL_ID="fake-model")
        out = subprocess.run([sys.executable, "-I", str(tmp_path / "app.py")], env=env,
                             capture_output=True, text=True, timeout=180)
        spans = recorder.spans()
        raw = recorder.raw()
    assert out.returncode != 0
    assert spans
    assert any(s["status"].get("code") == "STATUS_CODE_ERROR" for s in spans)
    assert b"Invalid API key" not in raw
    assert b"Traceback (most recent call last)" not in raw


def test_page_preserves_scope_without_unqualified_bus_setup():
    text = PAGE.read_text(encoding="utf-8")
    assert "LangGraph adapter" in text
    assert "FI_HIDE_INPUTS" in text and "FI_HIDE_OUTPUTS" in text
    assert "SpanProcessor" in text
    assert "AgentSpecInstrumentor().instrument" not in text
    assert "Other Agent Spec adapters and `Flow` components are outside" in text
    assert "How that was checked:" not in text
    assert "Agent Spec source read" not in text


def test_install_line_matches_requirements():
    requirements = (EXAMPLE / "requirements.txt").read_text(encoding="utf-8")
    pin = re.search(r"pyagentspec\[langgraph\]==([\d.]+)", requirements).group(1)
    text = PAGE.read_text(encoding="utf-8")
    assert f'pip install "pyagentspec[langgraph]=={pin}"' in text
    for package in ("traceai-langchain", "fi-instrumentation-otel"):
        version = re.search(re.escape(package) + r"==([\d.]+)", requirements).group(1)
        assert f'"{package}>={version}"' in text
