"""The docs page is a stop notice. These checks keep it one: pinned facts match the scripts, no setup steps."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PAGE = os.path.join(ROOT, "src", "pages", "docs", "integrations", "frameworks", "ai-sdk-cpp.mdx")
SCRIPT = os.path.join(HERE, "..", "check_pin.sh")


def read(path):
    with open(path) as f:
        return f.read()


class PageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = read(PAGE)
        cls.body = cls.page.split("---", 2)[2]

    def test_pin_in_page_matches_the_script(self):
        pin = re.search(r'CHECK_PIN_SHA:-([0-9a-f]{40})', read(SCRIPT)).group(1)
        self.assertIn(pin, self.page)

    def test_first_heading_is_about(self):
        self.assertEqual(re.findall(r"^#{2,3} (.+)$", self.body, re.M)[0], "About")

    def test_says_not_supported(self):
        self.assertIn("Not supported", self.page)
        self.assertIn("has no setup steps", self.page)

    def test_no_setup_steps_no_code_blocks(self):
        self.assertNotIn("```", self.page)
        for word in ("pip install", "npm install", "cmake -", "export FI_", "FI_API_KEY", "FI_SECRET_KEY"):
            self.assertNotIn(word, self.page)

    def test_makes_no_claim_that_a_trace_arrived(self):
        self.assertIn("No AI SDK C++ trace has been sent to Future AGI", self.page)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.page)

    def test_internal_links_resolve_to_pages(self):
        pages = os.path.join(ROOT, "src", "pages")
        for href in re.findall(r"\]\((/docs[^)#]*)\)", self.page):
            rel = href.rstrip("/")
            candidates = [os.path.join(pages, rel.lstrip("/") + ".mdx"), os.path.join(pages, rel.lstrip("/"), "index.mdx")]
            self.assertTrue(any(os.path.exists(c) for c in candidates), href)

    def test_every_search_in_the_table_is_run_by_the_script(self):
        script = read(SCRIPT)
        for term in ("otlp", "opentelemetry", "exporter", "traceparent", "gen_ai", "/v1/traces", "langfuse", "x-api-key"):
            self.assertIn(f"`{term}`", self.page)
            self.assertIn(term, script)


if __name__ == "__main__":
    unittest.main()
