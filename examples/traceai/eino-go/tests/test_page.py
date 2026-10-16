"""Checks that the CloudWeGo Eino docs page and this example stay in step.

No network, no Go toolchain: run with `python3 -m unittest discover -s tests -v`
from examples/traceai/eino-go.
"""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent.parent
PAGE = REPO / "src/pages/docs/integrations/traceai/go/eino.mdx"
MAIN = HERE / "main.go"
RUN = HERE / "run_e2e.sh"
README = HERE / "README.md"


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
        self.assertGreaterEqual(len(blocks), 7)
        main_lines = _code_lines(self.main)
        for block in blocks:
            with self.subTest(block=block.splitlines()[0]):
                self.assertTrue(
                    _is_subsequence(_code_lines(block), main_lines),
                    "a Go snippet on the page is not in main.go (in order)",
                )

    def test_exporter_is_configured_the_way_future_agi_needs(self):
        for needed in ('"X-Api-Key"', '"X-Secret-Key"', "otlptracehttp.NoCompression",
                       '"/tracer/v1/traces"', '"project_name"', '"project_type", "observe"',
                       "defer shutdown(h, tp)", "h.Shutdown(ctx)", "tp.Shutdown(ctx)"):
            self.assertIn(needed, self.main)
        code = "\n".join(_code_lines(self.main)).lower()
        self.assertFalse("gzip" in code, "main.go must not enable gzip")
        self.assertNotRegex(self.main, r"resource\.With(Host|Process|OS)")

    def test_handler_is_registered_once_before_any_run(self):
        self.assertEqual(self.main.count("callbacks.AppendGlobalHandlers("), 1)
        self.assertNotIn("compose.WithCallbacks(", self.main)
        self.assertNotIn("adk.WithCallbacks(", self.main)
        reg = self.main.index("callbacks.AppendGlobalHandlers(")
        self.assertLess(reg, self.main.index("runner.Query("))

    def test_future_agi_keys_stay_on_the_exporter(self):
        self.assertEqual(self.main.count('os.Getenv("FI_API_KEY")'), 1)
        self.assertEqual(self.main.count('os.Getenv("FI_SECRET_KEY")'), 1)
        self.assertIn('APIKey:  os.Getenv("OPENAI_API_KEY")', self.main)

    def test_page_states_versions_privacy_and_differences(self):
        for needed in ("v0.9.21", "v0.9.19", "v0.1.13", "Go 1.26", "1.27.2", "1.26.9", "v1.47.0",
                       "FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "__REDACTED__", "go/openai", "go/anthropic",
                       "go/genai", "eino-ext/callbacks/langfuse", "AppendGlobalHandlers", "SIGTERM",
                       "## Troubleshooting", "## Not supported", "## Privacy", "## What is captured",
                       "## Errors", "DeepAgent", "interrupt/resume"):
            self.assertIn(needed, self.page)

    def test_page_does_not_invent_usage_or_provider(self):
        self.assertIn("never a sum of chunks", self.page)
        self.assertIn("`gen_ai.provider.name` is not written", self.page)
        self.assertNotRegex(self.page, r"cost (is|are) (captured|recorded|computed by the module)")

    def test_run_script_builds_from_the_documented_modules_and_never_echoes_keys(self):
        run = RUN.read_text()
        self.assertIn('go get "github.com/future-agi/traceAI/go/eino@$REF"', run)
        self.assertIn("go get github.com/future-agi/traceAI/go/eino@latest", self.page)
        for key in ("FI_API_KEY", "FI_SECRET_KEY", "OPENAI_API_KEY"):
            self.assertNotRegex(run, r"echo[^\n]*\$\{?" + key)
        self.assertIn("FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true", run)
        self.assertIn('EINO_VERSION="${EINO_VERSION:-v0.9.21}"', run)

    def test_pinned_commit_and_pr_are_the_same_everywhere(self):
        readme = README.read_text()
        pins = set(re.findall(r"go/eino@([0-9a-f]{12})", self.page))
        pins |= set(re.findall(r"TRACEAI_GO_EINO_REF=([0-9a-f]{12})", readme))
        self.assertLessEqual(len(pins), 1, f"page and README pin different commits: {pins}")
        prs = set(re.findall(r"traceAI/pull/(\d+)", self.page)) | set(re.findall(r"PR\s+#(\d+)", readme))
        self.assertLessEqual(len(prs), 1, f"page and README name different PRs: {prs}")
        for placeholder in ("TRACEAI_PR", "TRACEAI_REF"):
            self.assertFalse(placeholder in self.page + readme, f"placeholder {placeholder} left in the page or README")


if __name__ == "__main__":
    unittest.main()
