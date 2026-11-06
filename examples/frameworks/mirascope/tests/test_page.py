"""The docs page and the example must not drift apart."""

from __future__ import annotations

import re
from pathlib import Path

from conftest import HERE

PAGE = HERE.parent.parent.parent / "src" / "pages" / "docs" / "integrations" / "frameworks" / "mirascope.mdx"


def _python_blocks(text: str) -> dict[str, str]:
    return {
        title: body
        for title, body in re.findall(r"```python title=\"([^\"]+)\"\n(.*?)\n```", text, flags=re.S)
    }


def test_the_page_carries_the_helper_verbatim():
    blocks = _python_blocks(PAGE.read_text())
    assert blocks["futureagi_tracing.py"].strip() == (HERE / "futureagi_tracing.py").read_text().strip()


def test_the_page_app_orders_configure_before_instrument():
    app = _python_blocks(PAGE.read_text())["app.py"]
    assert app.index("ops.configure(tracer_provider=provider)") < app.index("ops.instrument_llm()")
    assert "provider.shutdown()" in app
    assert "langfuse" not in app.lower()


def test_the_tested_version_is_pinned_everywhere():
    page = PAGE.read_text()
    requirements = (HERE / "requirements.txt").read_text()
    assert "mirascope[openai,anthropic,google,ops]==2.5.0" in requirements
    assert 'pip install "mirascope[openai,anthropic,google,ops]==2.5.0"' in page
    assert "Mirascope 2.5.0" in page


def test_the_page_follows_the_style_guide():
    page = PAGE.read_text()
    body = page.split("---", 2)[2]
    assert body.lstrip().startswith("Send Mirascope model and application spans")
    assert "self-hosted Future AGI" in body
    assert 'export FI_BASE_URL="http://localhost:4318"' in body
    assert "How this was checked" not in body
    assert "—" not in page, "no em-dashes"
    assert "## Next Steps" in page
    for heading in ("## What is captured", "## Privacy", "## Limitations", "## Troubleshooting"):
        assert heading in page


def test_every_attribute_the_page_says_is_kept_is_in_the_allow_list():
    from futureagi_tracing import METADATA_ATTRIBUTES

    for attribute in (
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "mirascope.ops.session.id",
        "error.type",
    ):
        assert attribute in METADATA_ATTRIBUTES
    for attribute in ("gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions", "gen_ai.tool.definitions", "error.message"):
        assert attribute not in METADATA_ATTRIBUTES
        assert f"`{attribute}`" in PAGE.read_text() or attribute == "error.message"


def test_the_pages_app_snippet_runs_as_written():
    """Run the app.py block from the page, unchanged except for the model id, against the fakes."""
    from conftest import MARKER, MODEL_ID, run_code

    snippet = _python_blocks(PAGE.read_text())["app.py"]
    assert "openai/gpt-4o-mini" in snippet
    run = run_code(snippet.replace("openai/gpt-4o-mini", MODEL_ID))
    assert run.returncode == 0, run.stderr
    assert "sunny, 24 C" in run.stdout or "weather report says" in run.stdout
    names = sorted(s["name"].split(" ")[0] for s in run.spans)
    assert names == ["Response.resume", "chat", "chat", "execute_tool", "weather_agent"]
    assert len({s["trace_id"] for s in run.spans}) == 1
    assert "Lisbon" not in run.everything(), "metadata only by default"
    assert MARKER not in run.everything()
