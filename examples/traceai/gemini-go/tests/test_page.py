"""Checks that the Gemini Go docs page and this example stay in step.

No network, no Go toolchain: run with `python3 -m unittest discover -s tests -v`
from examples/traceai/gemini-go.
"""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent.parent
PAGE = REPO / "src/pages/docs/integrations/traceai/go/gemini.mdx"
MAIN = HERE / "main.go"
RUN = HERE / "run_e2e.sh"


def _strip_comment(line: str) -> str:
    idx = line.find(" //")
    if idx >= 0 and line.count('"', 0, idx) % 2 == 0:
        line = line[:idx]
    return line.strip()


def _code_lines(src: str) -> list:
    out = []
    for raw in src.splitlines():
        line = _strip_comment(raw)
        if line and not line.startswith("//"):
            out.append(line)
    return out


def _go_blocks(page: str) -> list:
    return re.findall(r"```go\n(.*?)```", page, flags=re.S)


def _is_subsequence(needle: list, haystack: list) -> bool:
    it = iter(haystack)
    return all(any(line == h for h in it) for line in needle)


class PageMatchesExample(unittest.TestCase):
    page = PAGE.read_text()
    main = MAIN.read_text()

    def test_every_go_block_is_an_excerpt_of_main_go(self):
        blocks = _go_blocks(self.page)
        self.assertGreaterEqual(len(blocks), 6)
        main_lines = _code_lines(self.main)
        for block in blocks:
            with self.subTest(block=block.splitlines()[0]):
                self.assertTrue(
                    _is_subsequence(_code_lines(block), main_lines),
                    "a Go snippet on the page is not in main.go (in order)",
                )

    def test_exporter_and_hook_are_configured_the_way_future_agi_needs(self):
        for needed in ('"X-Api-Key"', '"X-Secret-Key"', "otlptracehttp.NoCompression",
                       '"/tracer/v1/traces"', '"project_name"', "defer shutdown(tp)",
                       "HTTPClient: traceaigenai.NewHTTPClient(", "genai.BackendGeminiAPI"):
            self.assertIn(needed, self.main)
        code = "\n".join(_code_lines(self.main)).lower()
        self.assertFalse("gzip" in code, "main.go must not enable gzip")
        self.assertNotRegex(self.main, r"resource\.With(Host|Process|OS)")
        self.assertNotIn("generative-ai-go", self.main)

    def test_page_states_versions_backend_privacy_and_differences(self):
        for needed in ("v1.75.0", "v1.71.0", "Go 1.26", "FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS",
                       "__REDACTED__", "github.com/google/generative-ai-go", "2025-11-30",
                       "BackendGeminiAPI", "Vertex AI", "ClientConfig.HTTPClient",
                       "/docs/integrations/traceai/google_genai", "/docs/integrations/traceai/java/llm-providers",
                       "## Troubleshooting", "## Not supported", "## Privacy", "## What is captured"):
            self.assertIn(needed, self.page)

    def test_run_script_builds_from_the_documented_module_and_never_echoes_keys(self):
        run = RUN.read_text()
        self.assertIn('go get "github.com/future-agi/traceAI/go/genai@$REF"', run)
        self.assertIn("go get github.com/future-agi/traceAI/go/genai@latest", self.page)
        for key in ("FI_API_KEY", "FI_SECRET_KEY", "GEMINI_API_KEY"):
            self.assertNotRegex(run, r"echo[^\n]*\$\{?" + key)
        self.assertIn("FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true", run)


if __name__ == "__main__":
    unittest.main()
