"""Check the published adapter guide, independently of the manual weather example."""
import asyncio
import re
import runpy
from pathlib import Path

import pytest
from temporalio import workflow
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from helpers import MockModel

PAGE = Path(__file__).resolve().parents[4] / "src/pages/docs/integrations/frameworks/temporal.mdx"


@pytest.fixture
def program(tmp_path, monkeypatch):
    # Import the exact files a reader copies. The workflow must be a real module
    # so Temporal can independently import it inside the replay sandbox.
    snippets = re.findall(r'<CodeGroup titles=\{\["([\w]+\.py)"\]\}>\s*```python\n(.*?)\n```', PAGE.read_text(), re.S)
    assert {name for name, _ in snippets} == {"returns_workflow.py", "run_return.py"}
    for name, source in snippets:
        (tmp_path / name).write_text(source + "\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    return runpy.run_path(str(tmp_path / "run_return.py"))


def test_workflow_loads_in_replay_sandbox(program):
    async def prepare():
        definition = workflow._Definition.must_from_class(program["ReturnWindow"])
        SandboxedWorkflowRunner().prepare_workflow(definition)

    asyncio.run(prepare())


@pytest.mark.parametrize(("days", "expected"), [(12, "Within the 30-day window"), (31, "Outside the 30-day window")])
def test_no_model_needed(program, monkeypatch, days, expected):
    monkeypatch.delenv("RIDGELINE_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert asyncio.run(program["check_return_window"](days)) == expected


def test_optional_reply_makes_one_request(program, monkeypatch):
    model = MockModel()
    try:
        monkeypatch.setenv("RIDGELINE_MODEL", "returns-test")
        monkeypatch.setenv("OPENAI_BASE_URL", model.base_url)
        assert asyncio.run(program["check_return_window"](12)) == "It is sunny in Lisbon."
        assert len(model.requests) == 1
        assert model.requests[0]["model"] == "returns-test"
        assert "Within the 30-day window" in model.requests[0]["messages"][0]["content"]
    finally:
        model.close()


def test_page_contract():
    text = PAGE.read_text()
    assert re.match(r'^---\ntitle: .+\ndescription: ".+"\n---\n\n## About\n', text)
    assert re.findall(r'^## (.+)$', text, re.M)[-1] == "Next steps"
    for term in ("traceAI-temporal==0.1.1", "FI_API_KEY", "FI_SECRET_KEY", "FI_PROJECT_NAME", "FI_TRACES_URL",
                 "X-Api-Key", "X-Secret-Key", "capture_content=True", "keep_error_text=True", "session.id"):
        assert term in text
    for internal in ("otel_sync_to_async", "bind_context", "futureagi/", "tfc/", "/Users/"):
        assert internal not in text
