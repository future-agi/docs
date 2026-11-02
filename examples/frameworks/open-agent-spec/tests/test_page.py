"""The docs page shows exactly what this example ships and tests.

* the ``futureagi_tracing.py`` implementation matches this directory's file (the page has a shorter module docstring);
* the ``app.py`` block on the page runs as written (model stand-in, loopback recorder);
* the Arize snippet on the page is what ``scripts/openinference_variant.py`` runs;
* the install line pins the version in requirements.txt.

Skipped when the example is used outside the docs repository.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
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


def test_tracing_file_on_the_page_is_the_shipped_file():
    on_page = block("futureagi_tracing.py")
    shipped = (EXAMPLE / "futureagi_tracing.py").read_text(encoding="utf-8")
    # Only the introductory module docstring differs; all executable code must match exactly.
    assert on_page.startswith('"""') and shipped.startswith('"""')
    assert on_page.split('"""', 2)[2] == shipped.split('"""', 2)[2]


def test_self_hosted_origin_is_set_explicitly():
    text = PAGE.read_text(encoding="utf-8")
    assert '\nexport FI_BASE_URL="http://localhost:4318"' in text
    assert '# export FI_BASE_URL=' not in text


def test_app_on_the_page_runs_as_written(tmp_path):
    shutil.copy(EXAMPLE / "futureagi_tracing.py", tmp_path / "futureagi_tracing.py")
    (tmp_path / "app.py").write_text(block("app.py"), encoding="utf-8")
    key = "model-key-" + secrets.token_hex(8)
    with Recorder() as recorder, FakeOpenAI(key) as fake:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OTEL_", "MODEL_"))}
        env.update(FI_API_KEY="fi-a", FI_SECRET_KEY="fi-b", FI_BASE_URL=recorder.origin,
                   FI_PROJECT_NAME="oas-page", MODEL_BASE_URL=fake.url, MODEL_API_KEY=key,
                   MODEL_ID="fake-model")
        out = subprocess.run([sys.executable, "app.py"], cwd=str(tmp_path), env=env,
                             capture_output=True, text=True, timeout=180)
        spans = recorder.spans()
    assert out.returncode == 0, out.stderr[-2000:]
    assert "It is sunny" in out.stdout
    assert [s["name"] for s in spans if not s["parentSpanId"]] == ["weather_assistant"]
    assert sorted(kind(s) for s in spans) == ["CHAIN"] * 4 + ["LLM"] * 2 + ["TOOL"]
    assert {s["resource"]["project_name"] for s in spans} == {"oas-page"}


def test_arize_snippet_matches_the_variant_script():
    text = PAGE.read_text(encoding="utf-8")
    variant = (EXAMPLE / "scripts" / "openinference_variant.py").read_text(encoding="utf-8")
    for line in ("tracer_provider = register(project_type=ProjectType.OBSERVE)",
                 "AgentSpecInstrumentor().instrument(tracer_provider=tracer_provider, mask_sensitive_information="):
        assert line in text and line in variant, line


def test_page_describes_setup_without_verification_diary():
    text = PAGE.read_text(encoding="utf-8")
    assert "LangGraph adapter" in text
    assert "FI_HIDE_INPUTS" in text and "FI_HIDE_OUTPUTS" in text
    assert "mask_sensitive_information=True" in text
    assert "How that was checked:" not in text
    assert "Agent Spec source read" not in text


def test_install_line_matches_requirements():
    requirements = (EXAMPLE / "requirements.txt").read_text(encoding="utf-8")
    pin = re.search(r"pyagentspec\[langgraph\]==([\d.]+)", requirements).group(1)
    assert f'pip install "pyagentspec[langgraph]=={pin}"' in PAGE.read_text(encoding="utf-8")
