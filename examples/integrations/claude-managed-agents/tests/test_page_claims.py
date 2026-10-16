"""Offline: the claims on the docs page must match the recorded spike (tests/fixtures/observed.json).
Run: python3 -I tests/test_page_claims.py   (standard library only)
"""
import json
import pathlib
import re
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
OBS = json.loads((HERE / "fixtures" / "observed.json").read_text())
ROOT = next(p for p in HERE.parents if (p / "src" / "pages" / "docs" / "integrations").exists())
PAGE = ROOT / "src/pages/docs/integrations/claude-managed-agents.mdx"
TEXT = PAGE.read_text()


def spans(label):
    return OBS["traces"][label]["spans"]


class PageClaims(unittest.TestCase):
    def test_front_matter_status_and_about(self):
        self.assertTrue(TEXT.startswith("---\ntitle:"))
        self.assertIn("not supported yet", TEXT.lower())
        self.assertIn("checked on 2026-10-16", TEXT)
        self.assertIn("\n## About\n", TEXT)
        self.assertEqual(TEXT.split("\n## ")[1].splitlines()[0], "About")  # first heading is About

    def test_no_setup_content_and_no_em_dash(self):
        self.assertNotRegex(TEXT, r"```(bash|sh|shell|yaml|python|typescript)")
        self.assertNotIn("OTEL_EXPORTER", TEXT)
        self.assertNotIn("\u2014", TEXT)

    def test_versions_on_page_match_fixture(self):
        self.assertIn(f"SDK {OBS['versions']['anthropic']}", TEXT)
        self.assertIn("managed-agents-2026-04-01", TEXT)

    def test_delivery_claims(self):
        rejected = next(r for r in OBS["delivery_probe"] if not r["project_name_added"])
        self.assertEqual([a["status"] for a in rejected["attempts"]], [400, 400])
        self.assertIn("have no project_name", rejected["attempts"][1]["body"])
        self.assertIn("ResourceSpan(s) have no project_name", TEXT)
        for run in (r for r in OBS["delivery_probe"] if r["project_name_added"]):
            self.assertEqual([(a["compression"], a["status"]) for a in run["attempts"]], [("gzip", 400), ("none", 200)])
        self.assertIn("The uncompressed resend is accepted", TEXT)

    def test_api_span_tree_and_types(self):
        s = spans("api_fixture_metadata_only")
        types = {(x["name"], x["type"]) for x in s}
        self.assertIn(("anthropic.session.turn", "unknown"), types)
        self.assertIn(("anthropic.model_request", "llm"), types)
        self.assertIn(("anthropic.tool_use bash", "tool"), types)
        toks = [x["tokens"] for x in s if x["name"] == "anthropic.model_request"]
        self.assertEqual(toks, [[1834, 41], [1907, 18]])
        self.assertIn("1,834 input / 41 output tokens", TEXT)
        self.assertIn("1,907 input / 18 output tokens", TEXT)
        self.assertTrue(all(x["input_bytes"] == 0 for x in spans("api_fixture_content")))  # content not promoted

    def test_failure_claims(self):
        errs = {x["name"] for x in spans("api_fixture_failure") if x["status"] == "ERROR"}
        self.assertEqual(errs, {"anthropic.session.turn", "anthropic.model_request"})
        sdk = {x["name"]: x["status"] for x in spans("sdk_failure")}
        self.assertEqual(sdk["anthropic.sessions.retrieve"], "ERROR")
        self.assertIn("not_found_error", TEXT)

    def test_sdk_tree_on_page(self):
        names = [x["name"] for x in spans("sdk_metadata_only")]
        for n in names:
            self.assertIn(n, TEXT)
        self.assertFalse({"anthropic.session.turn", "anthropic.model_request"} & set(names))
        tool = [x for x in spans("sdk_metadata_only") if x["name"].startswith("anthropic.custom_tool_use")]
        self.assertEqual(tool[0]["type"], "tool")

    def test_privacy_claims(self):
        ps = OBS["privacy_scan"]
        self.assertEqual(ps["marker_hits_by_run"]["sdk_metadata_only_marker"], {})
        self.assertEqual(set(ps["marker_columns"]["sdk_content_marker"]), {"attrs_string"})
        self.assertEqual(set(ps["marker_columns"]["api_fixture_content_marker"]), {"attrs_string"})
        self.assertTrue(all(v == {} for v in ps["local_identifiers_and_keys_hits"].values()))
        self.assertGreaterEqual(ps["tables_scanned"], 50)
        self.assertIn("ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content", TEXT)
        self.assertIn("Metadata only", TEXT)

    def test_standin_is_flagged(self):
        self.assertIn("stand-in", TEXT.lower())
        self.assertIn("No Anthropic account", OBS["standin"])
        self.assertRegex(TEXT, r"No spend was approved")

    def test_links_and_sources(self):
        for url in ("https://platform.claude.com/docs/en/manage-claude/opentelemetry/api",
                    "https://platform.claude.com/docs/en/manage-claude/opentelemetry/sdk",
                    "https://platform.claude.com/docs/en/api/opentelemetry/spans"):
            self.assertIn(url, TEXT)
        for internal in re.findall(r"\]\((/docs/[^)#]+)", TEXT):
            target = ROOT / "src/pages" / (internal.lstrip("/") + ".mdx")
            index = ROOT / "src/pages" / internal.lstrip("/") / "index.mdx"
            self.assertTrue(target.exists() or index.exists(), internal)

    def test_no_secrets_or_local_names(self):
        blob = TEXT + json.dumps(OBS)
        for bad in ("/Users/", "X-Secret-Key=", "sk-ant-", "MacBook"):
            self.assertNotIn(bad, blob)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
