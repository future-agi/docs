"""Contract test for the hosted-Devin docs page (docs-only, no connector).

Checks that the page names the surfaces Devin documents, says none of them
is a session trace export, does not invent a Devin endpoint, a Devin
credential setting, a Future AGI trace sink for Devin (PRD R-01/R-02) or a
Cascade hook configuration (that belongs to the Devin Desktop page), and that
the untested Devin SDK path is described content-off first.

    python3 examples/coding-agents/devin/test_page.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGES = ROOT / "src/pages"
PAGE = PAGES / "docs/integrations/coding-agents/devin.mdx"
DESKTOP_HREF = "/docs/integrations/coding-agents/devin-desktop"


def section(text: str, heading: str) -> str:
    """Body of a '## '/'### ' section up to the next heading of the same or higher level."""
    level = heading.split(" ", 1)[0]
    start = text.index(heading + "\n")
    stop = re.compile(r"^#{1,%d} " % len(level), re.M)
    match = stop.search(text, start + len(heading) + 1)
    return text[start: match.start() if match else len(text)]


class DevinPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PAGE.read_text(encoding="utf-8")

    def test_names_every_documented_surface(self):
        for needle in ("docs.devin.ai/product-guides/automations", "docs.devin.ai/integrations/slack",
                       "docs.devin.ai/integrations/microsoft-teams", "session-insights",
                       "audit-logs", "devin_session_events", "docs.devin.ai/sdk/guides/tracing",
                       "lifecycle-hooks"):
            self.assertIn(needle, self.text, needle)

    def test_states_unsupported_with_check_date(self):
        self.assertIn("not supported", self.text.splitlines()[1])
        self.assertIn("last checked against [docs.devin.ai](https://docs.devin.ai) on 2026-10-15", self.text)
        self.assertIn("No OTLP endpoint, outbound webhook for session events, or hook that runs for cloud sessions is documented", self.text)

    def test_about_does_not_claim_devin_sends_nothing_outbound(self):
        # Devin does send notifications and chat replies; the claim is about session steps.
        about = section(self.text, "## About")
        self.assertNotIn("does not send session activity", about)
        self.assertIn("does not export a session's steps or tool calls to an endpoint you configure", about)

    def test_no_invented_devin_endpoint_or_credential(self):
        # The only Devin URLs are documentation links; no api.devin.ai endpoint is given.
        self.assertNotIn("api.devin.ai", self.text)
        self.assertIsNone(re.search(r"DEVIN_API_KEY\s*=", self.text))
        # Future AGI settings on this page take no Devin secret.
        self.assertIsNone(re.search(r"FI_[A-Z_]*DEVIN", self.text))

    def test_no_future_agi_trace_sink_for_devin(self):
        # PRD R-01 "No sample endpoint", R-02 "No Future AGI URL for Devin to call as a trace sink".
        for needle in ("tracer/v1/traces", "api.futureagi.com", "X-Api-Key", "X-Secret-Key", "project_name"):
            self.assertNotIn(needle, self.text, needle)

    def test_sdk_path_is_untested_and_content_off_first(self):
        sdk = section(self.text, "### Devin SDK tracing (untested)")
        self.assertIn("has not tested this path", sdk)
        self.assertIn("does not support it as an integration", sdk)
        # The recordContent advice is the first caveat, not a footnote.
        bullets = [line for line in sdk.splitlines() if line.startswith("- ")]
        self.assertIn("recordContent: false", bullets[0])
        self.assertIn("recorded by default", bullets[0])
        self.assertIn("unless you want that text", bullets[0])
        self.assertIn("Each Devin turn is its own trace unless you pass a `parent` span", sdk)

    def test_privacy_section(self):
        privacy = section(self.text, "## Privacy")
        self.assertIn("Hosted Devin sends nothing to Future AGI", privacy)
        self.assertIn("never asks for a Devin API key", privacy)
        self.assertIn("recordContent: false", privacy)
        self.assertIn("by default", privacy)

    def test_devin_desktop_reference_is_linked_or_not_claimed(self):
        desktop_page = PAGES / (DESKTOP_HREF.lstrip("/") + ".mdx")
        if desktop_page.exists():
            # Once the Desktop page is in the tree, refer to it by link, never as plain bold text.
            self.assertIn(f"]({DESKTOP_HREF})", self.text)
        else:
            # No page to point at: do not claim Future AGI supports Cascade, and do not link a missing page.
            self.assertNotIn(DESKTOP_HREF, self.text)
            self.assertNotIn("Future AGI supports", self.text)
            self.assertIn("recipe for Devin Desktop is in progress", self.text)
        self.assertNotIn("see **Devin Desktop**", self.text)

    def test_no_cascade_or_local_hook_configuration(self):
        for needle in ("hooks.json", "pre_user_prompt", "post_cascade_response", "trajectory_id", "emit.py"):
            self.assertNotIn(needle, self.text, needle)

    def test_internal_links_resolve(self):
        for href in re.findall(r"\]\((/docs/[^)#\s]+)", self.text):
            page = PAGES / (href.lstrip("/") + ".mdx")
            index = PAGES / href.lstrip("/") / "index.mdx"
            self.assertTrue(page.exists() or index.exists(), href)

    def test_style_headings(self):
        self.assertIn("\n## Next Steps\n", self.text)
        self.assertNotIn("\n## Next steps\n", self.text)


if __name__ == "__main__":
    unittest.main()
