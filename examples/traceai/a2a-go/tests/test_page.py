"""Page/example contracts, run by the A2A Go documentation GitHub workflow."""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent.parent
PAGE = REPO / "src/pages/docs/integrations/traceai/go/a2a.mdx"
MAIN = HERE / "main.go"
RUN = HERE / "run_e2e.sh"
README = HERE / "README.md"
WORKFLOW = REPO / ".github/workflows/a2a-go-docs.yml"


def _strip_comment(line: str) -> str:
    idx = line.find(" //")
    if idx >= 0 and line.count('"', 0, idx) % 2 == 0:
        line = line[:idx]
    return line.strip()


def _code_lines(src: str) -> list:
    return [line for raw in src.splitlines()
            if (line := _strip_comment(raw)) and not line.startswith("//")]


def _is_subsequence(needle: list, haystack: list) -> bool:
    it = iter(haystack)
    return all(any(line == h for h in it) for line in needle)


class PageMatchesExample(unittest.TestCase):
    page = PAGE.read_text()
    main = MAIN.read_text()

    def test_every_go_block_is_an_excerpt_of_main_go(self):
        blocks = re.findall(r"```go\n(.*?)```", self.page, flags=re.S)
        self.assertGreaterEqual(len(blocks), 7)
        main_lines = _code_lines(self.main)
        for block in blocks:
            with self.subTest(block=block.splitlines()[0]):
                self.assertTrue(
                    _is_subsequence(_code_lines(block), main_lines),
                    "a Go snippet on the page is not in main.go (in order)",
                )

    def test_exporter_configuration_and_credential_boundary(self):
        for needed in ('"X-Api-Key"', '"X-Secret-Key"', "otlptracehttp.NoCompression",
                       '"/tracer/v1/traces"', '"project_name"', '"project_type", "observe"',
                       "defer shutdown(tp)"):
            self.assertIn(needed, self.main)
            self.assertIn(needed, self.page)
        self.assertNotIn("gzip", "\n".join(_code_lines(self.main)).lower())
        self.assertNotRegex(self.main, r"resource\.With(Host|Process|OS)")
        for key in ("FI_API_KEY", "FI_SECRET_KEY"):
            self.assertEqual(self.main.count(f'os.Getenv("{key}")'), 1)
        self.assertNotIn("AttachServiceParams", self.main)

    def test_maintained_client_and_server_complete_streams(self):
        for src in (self.main, self.page):
            for needed in ("traceaia2a.NewClientFromCard(",
                           "a2aclient.WithCallInterceptors(traceaia2a.NewInterceptor(",
                           "traceaia2a.WrapHandler(", "traceaia2a.NewServerInterceptor("):
                self.assertIn(needed, src)
            self.assertNotIn("propagation.MapCarrier", src)
            self.assertNotIn("a2aclient.NewFromCard(", src)
        self.assertIn("client *traceaia2a.Client", self.main)
        for needed in ("Normal EOF", "breaking out early", "auth-required", "deadline",
                       "not its embedded `.Client`", "`Wrap` method", "process-local"):
            self.assertIn(needed, self.page)
        self.assertNotIn('tracer.Start(ctx, "trip-helper"', self.main)

    def test_runnable_bootstrap_and_released_pins_match(self):
        workflow = WORKFLOW.read_text()
        install = re.search(r"```bash\n(.*?)```", self.page, flags=re.S).group(1)
        for needed in ("mkdir a2a-go-example", "cd a2a-go-example", "curl -fsSLO",
                       "go mod init example.com/a2a-go-example", "go mod tidy"):
            self.assertIn(needed, install)
        for pin in ("github.com/future-agi/traceAI/go/a2a@v0.1.1",
                    "github.com/a2aproject/a2a-go/v2@v2.7.0",
                    "go.opentelemetry.io/otel/sdk@v1.47.0",
                    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.47.0"):
            for src in (self.page, README.read_text(), workflow):
                self.assertIn(pin, src)
        self.assertLess(self.page.index("go mod init"), self.page.index("go run ."))
        self.assertIn("Go 1.26.0", self.page)
        self.assertNotRegex(self.page, r"@latest|v2\.[56]\.0")
        run = RUN.read_text()
        self.assertIn('REF="${TRACEAI_GO_A2A_REF:-v0.1.1}"', run)
        self.assertIn('A2A_GO_VERSION="${A2A_GO_VERSION:-v2.7.0}"', run)
        for key in ("FI_API_KEY", "FI_SECRET_KEY", "OPENAI_API_KEY"):
            self.assertNotRegex(run, r"echo[^\n]*\$\{?" + key)

    def test_privacy_and_scope_are_actionable_not_a_test_diary(self):
        for needed in ("FI_HIDE_INPUTS=true", "FI_HIDE_OUTPUTS=true", "FI_HIDE_ERROR_DETAILS=true",
                       "__REDACTED__", "setting it to `false`", "independently in each process", "SIGTERM",
                       "never an LLM span", "ListTasks", "## Privacy", "## Troubleshooting",
                       "/docs/command-center/features/mcp-a2a"):
            self.assertIn(needed, self.page)
        self.assertNotRegex(self.page, r"(?i)tested with|tested surface|in our test|verified live|run_e2e|2026-10-16")
        self.assertNotIn("does not instrument the server", self.page)


if __name__ == "__main__":
    unittest.main()
