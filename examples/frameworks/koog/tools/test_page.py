"""Keeps the docs page and this example in step. Standard library only, no JDK.

Run from this directory:  python3 -m unittest -v test_page
"""
import pathlib
import re
import unittest

EXAMPLE = pathlib.Path(__file__).resolve().parents[1]
DOCS_ROOT = EXAMPLE.parents[2]
PAGE = DOCS_ROOT / "src/pages/docs/integrations/frameworks/koog.mdx"
SRC = EXAMPLE / "src/main/kotlin/ai/futureagi/examples/koog"


def read(path):
    return path.read_text(encoding="utf-8")


def section(page, heading):
    start = page.index(heading)
    nxt = page.find("\n## ", start + len(heading))
    return page[start:nxt if nxt != -1 else len(page)]


def first_kotlin_block(text):
    m = re.search(r"```kotlin\n(.*?)```", text, re.S)
    assert m, "no kotlin block"
    return m.group(1)


class PageMatchesExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = read(PAGE)
        cls.telemetry = read(SRC / "FutureAgiTelemetry.kt")
        cls.exporter = read(SRC / "FutureAgiSpanExporter.kt")

    def test_quickstart_snippet_is_the_compiled_file(self):
        snippet = first_kotlin_block(section(self.page, "## 4. Install it on your agent"))
        quickstart = read(SRC / "quickstart/Quickstart.kt")
        body = quickstart.split("import ai.futureagi.examples.koog.FutureAgiTelemetry\n", 1)[1].lstrip("\n")
        self.assertEqual(snippet, body)

    def test_setup_snippet_lines_exist_in_the_setup_class(self):
        snippet = first_kotlin_block(section(self.page, "## 3. Copy the two setup files"))
        for needle in [
            "/tracer/v1/traces",
            '.addHeader("X-Api-Key", config.apiKey)',
            '.addHeader("X-Secret-Key", config.secretKey)',
            '.setCompression("none")',
            ".setMeterProvider(MeterProvider.noop())",
            '"project_name" to config.projectName',
            '"project_type" to "observe"',
            "otel.setVerbose(config.captureContent)",
            "otel.setSdk(sdk)",
            "forceFlush()",
            "batchSpanProcessor(spanExporter.toOtelKotlinSpanExporter())",
        ]:
            self.assertIn(needle, snippet, needle)
            self.assertIn(needle, self.telemetry, needle)

    def test_versions_match_gradle_properties(self):
        props = dict(
            line.split("=", 1) for line in read(EXAMPLE / "gradle.properties").splitlines()
            if "=" in line and not line.startswith("#")
        )
        deps = first_kotlin_block(section(self.page, "## 1. Add dependencies"))
        self.assertIn('"ai.koog:koog-agents:%s"' % props["koogVersion"], deps)
        self.assertIn('"io.opentelemetry:opentelemetry-bom:%s"' % props["otelVersion"], deps)

    def test_env_names_match(self):
        for name in ["FI_BASE_URL", "FI_API_KEY", "FI_SECRET_KEY", "FI_PROJECT_NAME", "OTEL_SERVICE_NAME",
                     "FI_KOOG_CAPTURE_CONTENT"]:
            self.assertIn(name, self.page, name)
            self.assertIn('"%s"' % name, self.telemetry, name)

    def test_privacy_section_lists_only_masked_keys(self):
        privacy = section(self.page, "## Privacy")
        listed = re.findall(r"`((?:gen_ai|koog)\.[a-z_.]+|system_instructions)`", privacy)
        self.assertTrue(listed)
        for key in listed:
            self.assertIn('"%s"' % key, self.exporter, key)

    def test_example_links_resolve(self):
        links = re.findall(r"github\.com/future-agi/docs/tree/main/(examples/[^)\s]+)", self.page)
        self.assertTrue(links)
        for rel in links:
            self.assertTrue((DOCS_ROOT / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
