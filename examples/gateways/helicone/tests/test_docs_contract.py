"""Guard the supported privacy scope and offline conformance coverage."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GUIDE = ROOT / "src/pages/docs/integrations/gateways/helicone.mdx"
WORKFLOW = ROOT / ".github/workflows/pr-checks.yml"


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
