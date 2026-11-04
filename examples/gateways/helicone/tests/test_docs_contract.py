"""Guard the supported privacy/streaming scope and offline conformance coverage."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
GUIDE = ROOT / "src/pages/docs/integrations/gateways/helicone.mdx"
README = ROOT / "examples/gateways/helicone/README.md"
WORKFLOW = ROOT / ".github/workflows/pr-checks.yml"


@pytest.mark.parametrize("document", [GUIDE, README])
def test_streaming_limits_are_explicit(document):
    text = document.read_text().replace("**", "")
    assert "Non-streamed calls" in text
    assert "Streamed calls in both SDKs retain the requested model" in text
    assert "Use non-streamed calls when you need the resolved model identity" in text
    assert "`@traceai/openai` 0.1.15 does not map streamed Chat Completions token usage to span attributes" in text
    assert "even with `stream_options: { include_usage: true }`" in text
    assert "Use Python when you need streamed token metrics" in text
    assert 'stream_options={"include_usage": True}' in text


def test_lead_and_troubleshooting_do_not_overpromise_streams():
    text = GUIDE.read_text()
    lead = text.split("## Install")[0]
    assert "Non-streamed calls include the returned model and token usage" in lead
    troubleshooting = text.split("## Troubleshooting")[1]
    assert "TypeScript `@traceai/openai` 0.1.15 does not map streamed usage, even with `include_usage`" in troubleshooting
    assert "Both SDKs retain the requested model for streams" in troubleshooting


def test_typescript_privacy_limit_is_explicit():
    text = GUIDE.read_text()
    assert "The TypeScript SDK does not mask tool definitions or `gen_ai.request.parameters`" in text
    assert "Use the Python SDK when tool schemas or invocation parameters are sensitive" in text
    assert "FI_HIDE_LLM_INVOCATION_PARAMETERS=true" in text


def test_conformance_runs_for_both_sdk_floors_and_latest_in_pr_ci():
    text = WORKFLOW.read_text()
    assert "test_helicone_conformance" in text
    assert "1.69.0" in text and "3.42.1" in text
    assert "4.0.0" in text and "7.47.0" in text
    assert "sandbox-exec" not in text  # GitHub's Linux runners have no macOS sandbox-exec.
