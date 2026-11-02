"""Regression contracts for security, workspace scope, and acceptance status."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]
PAGE = (ROOT / "src/pages/docs/integrations/claude-managed-agents.mdx").read_text()
SCRIPT = (ROOT / "examples/integrations/claude-managed-agents/run_collector_e2e.sh").read_text()


class ReviewRegressions(unittest.TestCase):
    def test_plaintext_port_is_loopback_only(self):
        self.assertIn("-p 127.0.0.1:4318:4318", PAGE)
        self.assertNotIn(" -p 4318:4318", PAGE)

    def test_secret_values_are_exported_before_docker_run(self):
        setup = PAGE.split("docker run -d", 1)[0]
        for name in ("ANTHROPIC_DEST_TOKEN", "FI_API_KEY", "FI_SECRET_KEY"):
            self.assertRegex(setup, rf"export {name}\b")
        self.assertIn('env.ANTHROPIC_DEST_TOKEN', PAGE)

    def test_api_example_selects_only_a_named_workspace(self):
        self.assertIn('workspaces:{type:"include", workspace_ids:[$workspace]}', PAGE)
        self.assertNotIn('"workspaces": {"type": "all"}', PAGE)

    def test_acceptance_script_requires_verification_and_exits_failed(self):
        self.assertIn('"${VERIFY:?Set VERIFY to fi_verify.py for acceptance}"', SCRIPT)
        self.assertIn('exit "$FAILED"', SCRIPT)
        self.assertNotIn("fi_verify skipped", SCRIPT)
        self.assertRegex(SCRIPT, r'if ! send ')

    def test_customer_page_has_no_internal_qualification_diary(self):
        for phrase in ("fixture-based", "Publication gate:", "not tried with this recipe", "Not yet qualified.", "no real destination"):
            self.assertNotIn(phrase, PAGE)


if __name__ == "__main__":
    unittest.main()
