"""Contract test for the hosted-Devin docs page (docs-only, no connector).

Checks that the page names the surfaces Devin documents, says none of them
is a session trace export, and does not invent a Devin endpoint, a Devin
credential setting, or a Cascade hook configuration (that belongs to the
Devin Desktop page).

    python3 examples/coding-agents/devin/test_page.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "src/pages/docs/integrations/coding-agents/devin.mdx"


class DevinPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PAGE.read_text(encoding="utf-8")

    def test_names_every_documented_surface(self):
        for needle in ("docs.devin.ai/product-guides/automations", "session-insights",
                       "audit-logs", "devin_session_events", "docs.devin.ai/sdk/guides/tracing",
                       "lifecycle-hooks"):
            self.assertIn(needle, self.text, needle)

    def test_states_unsupported_with_check_date(self):
        self.assertIn("not supported", self.text.splitlines()[1])
        self.assertIn("2026-10-14", self.text)
        self.assertIn("No OTLP endpoint, outbound webhook for session events, or hook that runs for cloud sessions is documented", self.text)

    def test_no_invented_devin_endpoint_or_credential(self):
        # The only Devin URLs are documentation links; no api.devin.ai endpoint is given.
        self.assertNotIn("api.devin.ai", self.text)
        self.assertIsNone(re.search(r"DEVIN_API_KEY\s*=", self.text))
        # Future AGI settings on this page take no Devin secret.
        self.assertIsNone(re.search(r"FI_[A-Z_]*DEVIN", self.text))

    def test_no_cascade_or_local_hook_configuration(self):
        for needle in ("hooks.json", "pre_user_prompt", "post_cascade_response", "trajectory_id", "emit.py"):
            self.assertNotIn(needle, self.text, needle)


if __name__ == "__main__":
    unittest.main()
