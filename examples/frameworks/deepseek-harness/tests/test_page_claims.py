"""Offline: the claims on the docs page must match the recorded spike fixture. Run: python3 -I tests/test_page_claims.py"""
import json, pathlib, re, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
FIX = json.loads((HERE / "fixtures" / "spike_observed.json").read_text())
PAGE = next(p for p in HERE.parents if (p / "src" / "pages" / "docs" / "integrations").exists()) \
    / "src/pages/docs/integrations/deepseek-harness.mdx"
TEXT = PAGE.read_text()


class PageClaims(unittest.TestCase):
    def test_front_matter_and_status(self):
        self.assertTrue(TEXT.startswith("---\ntitle:"))
        self.assertIn("not supported yet", TEXT.lower())
        self.assertIn("checked on 2026-10-16", TEXT)

    def test_no_setup_content(self):
        self.assertNotIn("```bash", TEXT)
        self.assertNotIn("OTEL_EXPORTER", TEXT)
        self.assertNotRegex(TEXT, r"(?i)\bnpm (i|install)\b|dsh plugin")

    def test_tested_versions_match_fixture(self):
        for v in set(FIX["dsh"].values()):
            self.assertIn(v, TEXT)
        self.assertIn(FIX["plugin"].split()[-1], TEXT)

    def test_content_off_marker_absent_on_marker_present(self):
        ms = FIX["marker_scan"]
        self.assertTrue(all(n == 0 for n in ms["content_off_markers_found"].values()))
        self.assertGreater(ms["content_on_marker_columns"]["spans.attrs_string"], 0)

    def test_page_admits_local_info_exported(self):
        self.assertTrue(FIX["marker_scan"]["local_info_in_content_off_runs"]["hostname_columns"])
        self.assertIn("dsh.session.cwd", TEXT)
        self.assertIn("host.name", TEXT)

    def test_failure_and_tool_error_claims(self):
        t = FIX["traces"]
        self.assertTrue(any(s["status"] == "ERROR" for s in t["alpha-bad-model"]["spans"]))
        tool = [s for s in t["alpha-tool-exit-3"]["spans"] if s["type"] == "tool"]
        self.assertTrue(tool and all(s["status"] == "OK" for s in tool))

    def test_span_tree_on_page_matches_fixture(self):
        names = [s["name"] for s in FIX["traces"]["alpha-content-off"]["spans"]]
        for n in ("enter_ai_application_system", "invoke_agent deepseek-harness", "react step", "execute_tool bash"):
            self.assertIn(n, names)
            self.assertIn(n, TEXT)

    def test_no_secrets_or_local_names(self):
        for bad in ("nikhilpareek", "/Users/", "Nikhils-MacBook", "X-Secret-Key="):
            self.assertNotIn(bad, TEXT)
            self.assertNotIn(bad, json.dumps(FIX))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
