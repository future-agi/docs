"""check_pin.sh against tiny synthetic git trees: it must say yes only when it should (no network)."""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "check_pin.sh")


def make_tree(files):
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", d], check=True)
    for path, text in files.items():
        full = os.path.join(d, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
    subprocess.run(["git", "-C", d, "add", "-A"], check=True)
    subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "x"], check=True)
    return d


def run(tree):
    p = subprocess.run(["bash", SCRIPT, tree], capture_output=True, text=True)
    return p.returncode, p.stdout


CONTROLS = {"include/langfuse.h": "// Langfuse client\n", "src/anthropic.cpp": 'headers["x-api-key"] = key;\n'}


class CheckPinTest(unittest.TestCase):
    def test_tree_without_otlp_passes(self):
        code, out = run(make_tree(dict(CONTROLS)))
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT: no OTLP or OpenTelemetry export", out)
        self.assertIn("otlp           0 files", out)

    def test_positive_control_otlp_in_tree_is_detected(self):
        for term, text in [("otlp", "// OTLP exporter\n"), ("opentelemetry", "#include <opentelemetry/sdk.h>\n"),
                           ("path", 'auto p = "/v1/traces";\n'), ("exp", "class SpanExporter {};\n")]:
            with self.subTest(term=term):
                files = dict(CONTROLS)
                files["src/tracing.cpp"] = text
                code, out = run(make_tree(files))
                self.assertEqual(code, 1, out)
                self.assertIn("reopen TH-8251", out)

    def test_search_that_cannot_find_its_controls_is_not_trusted(self):
        code, out = run(make_tree({"README.md": "nothing relevant\n"}))
        self.assertEqual(code, 2, out)
        self.assertIn("search not trusted", out)

    def test_not_a_git_checkout(self):
        code, _ = run(tempfile.mkdtemp())
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
