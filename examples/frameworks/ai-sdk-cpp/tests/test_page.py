"""The page preserves the unsupported boundary and actionable privacy warning."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PAGE = os.path.join(ROOT, "src", "pages", "docs", "integrations", "frameworks", "ai-sdk-cpp.mdx")


class PageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PAGE) as f:
            cls.page = f.read()

    def test_says_direct_tracing_is_not_supported(self):
        self.assertIn("not supported as a direct tracing integration", self.page)
        self.assertIn("not the OTLP traces", self.page)
        self.assertIn("Do not point its Langfuse host", self.page)

    def test_preserves_capture_warning(self):
        for phrase in ("prompts", "tool arguments and results", "model output", "provider error text", "does not provide a switch to omit"):
            self.assertIn(phrase, self.page)

    def test_source_audit_script_retains_pin_and_searches(self):
        with open(os.path.join(HERE, "..", "check_pin.sh")) as f:
            script = f.read()
        self.assertIn("9d8cd18200a33b64460c9101ed0dd6d4988bea61", script)
        for term in ("otlp", "opentelemetry", "exporter", "traceparent", "gen_ai", "/v1/traces", "langfuse", "x-api-key"):
            self.assertIn(term, script)

    def test_no_setup_steps_or_code_blocks(self):
        self.assertNotIn("```", self.page)
        for word in ("pip install", "npm install", "cmake -", "export FI_", "FI_API_KEY", "FI_SECRET_KEY"):
            self.assertNotIn(word, self.page)

    def test_no_internal_verification_diary(self):
        for phrase in ("What was checked", "Observed on the pinned build", "local stand-in", "2026-10-16"):
            self.assertNotIn(phrase, self.page)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.page)

    def test_internal_links_resolve_to_pages(self):
        pages = os.path.join(ROOT, "src", "pages")
        for href in re.findall(r"\]\((/docs[^)#]*)\)", self.page):
            rel = href.rstrip("/")
            candidates = [os.path.join(pages, rel.lstrip("/") + ".mdx"), os.path.join(pages, rel.lstrip("/"), "index.mdx")]
            self.assertTrue(any(os.path.exists(c) for c in candidates), href)


if __name__ == "__main__":
    unittest.main()
