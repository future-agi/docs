"""The snippet the docs page shows, run as a customer would, and checked against the page."""

from __future__ import annotations

import re
from pathlib import Path

from conftest import ROOT, by_name

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "frameworks" / "agentscope.mdx"


def test_quickstart_traces_to_the_project_it_names(run_app, collector):
    out = run_app(script="quickstart.py")
    assert out.returncode == 0, out.stderr
    assert "Answer:" in out.stdout
    spans = collector.spans()
    assert {s["_resource"]["project_name"] for s in spans} == {"my-chatbot"}
    assert [len(by_name(spans, p)) for p in ("invoke_agent weather-agent", "chat ", "execute_tool get_weather")] == [1, 2, 1]


def _blocks(text: str) -> dict[str, str]:
    """Code blocks of the page, keyed by their title attribute."""
    found = {}
    for match in re.finditer(r"```(\w+)(?: title=\"([^\"]+)\")?\n(.*?)```", text, re.S):
        if match.group(2):
            found[match.group(2)] = match.group(3)
    return found


def test_page_shows_the_files_in_this_folder():
    """The page's code blocks titled futureagi_tracing.py and quickstart.py are these files."""
    blocks = _blocks(PAGE.read_text())
    for name in ("futureagi_tracing.py", "quickstart.py"):
        assert name in blocks, f"the page has no code block titled {name}"
        assert blocks[name] == (ROOT / name).read_text(), f"the page's {name} differs from the file in the example"
