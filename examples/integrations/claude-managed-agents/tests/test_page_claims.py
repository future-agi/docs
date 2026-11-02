"""Offline: the docs page, the collector recipe and the fixture must agree.
Run: python -I tests/test_page_claims.py   (needs pyyaml and opentelemetry-proto)
"""
import pathlib
import re
import sys
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "spike"))
from fixture import build  # noqa: E402

ROOT = next(p for p in HERE.parents if (p / "src" / "pages" / "docs" / "integrations").exists())
TEXT = (ROOT / "src/pages/docs/integrations/claude-managed-agents.mdx").read_text()
RECIPE_PATH = HERE.parent / "otelcol.yaml"
RECIPE = RECIPE_PATH.read_text()
CFG = yaml.safe_load(RECIPE)

# Content attributes in https://platform.claude.com/docs/en/api/opentelemetry/spans (read 2026-10-20)
CONTENT_KEYS = ["gen_ai.system_instructions", "gen_ai.input.messages", "gen_ai.output.messages",
                "gen_ai.tool.call.arguments", "anthropic.tool_result.content",
                "anthropic.session.outcome_evaluation.explanation"]


def statements():
    out = []
    for block in CFG["processors"]["transform/anthropic"]["trace_statements"]:
        out += block["statements"]
    return "\n".join(out)


class Page(unittest.TestCase):
    def test_front_matter_and_style(self):
        self.assertTrue(TEXT.startswith("---\ntitle:"))
        self.assertIn("\n## About\n", TEXT)
        self.assertNotIn("—", TEXT)
        self.assertNotIn("not supported", TEXT.lower())

    def test_page_embeds_the_recipe_exactly(self):
        block = re.search(r"```yaml\n(.*?)```", TEXT, re.S).group(1)
        self.assertEqual(block, RECIPE)

    def test_stand_in_is_stated(self):
        self.assertIn("Draft setup: do not use with production data yet", TEXT)
        self.assertIn("A real Managed Agents session", TEXT)
        self.assertIn("Managed Agents-enabled, billed API key", TEXT)

    def test_draft_gate_and_explicit_content_toggle(self):
        self.assertIn("Publication gate:", TEXT)
        self.assertIn('-e FI_CAPTURE_CONTENT="${FI_CAPTURE_CONTENT:-false}"', TEXT)
        self.assertIn("docker rm -f cma-otelcol", TEXT)
        self.assertNotRegex(TEXT.lower(), r"not tested|untested|unverified")

    def test_both_setup_paths_and_beta_header(self):
        self.assertIn("settings/telemetry-destinations", TEXT)
        self.assertIn("telemetry-destinations-2026-08-11", TEXT)
        self.assertIn("traceparent", TEXT)

    def test_limits_stated(self):
        for s in ("At-least-once", "No zero data retention", "Beta."):
            self.assertIn(s, TEXT)


class Recipe(unittest.TestCase):
    def test_pipeline_and_exporter(self):
        p = CFG["service"]["pipelines"]["traces"]
        self.assertEqual(p["processors"], ["resource/future_agi", "transform/anthropic", "batch"])
        exp = CFG["exporters"]["otlp_http/future_agi"]
        self.assertEqual(exp["compression"], "none")
        self.assertEqual(exp["encoding"], "proto")
        self.assertEqual(set(exp["headers"]), {"X-Api-Key", "X-Secret-Key"})

    def test_receiver_is_authenticated(self):
        http = CFG["receivers"]["otlp"]["protocols"]["http"]
        self.assertEqual(http["auth"]["authenticator"], "bearertokenauth/anthropic")
        self.assertEqual(CFG["extensions"]["bearertokenauth/anthropic"]["scheme"], "Bearer")

    def test_project_name_stamped(self):
        attrs = {a["key"]: a for a in CFG["processors"]["resource/future_agi"]["attributes"]}
        self.assertEqual(attrs["project_name"]["action"], "upsert")
        self.assertEqual(attrs["project_type"]["value"], "observe")

    def test_span_kind_mapping(self):
        s = statements()
        for op, kind in (("invoke_agent", "AGENT"), ("chat", "LLM"), ("execute_tool", "TOOL")):
            self.assertRegex(s, rf'"fi.span.kind"\], "{kind}"\) where attributes\["gen_ai.operation.name"\] == "{op}"')
        self.assertIn('attributes["session.id"], attributes["anthropic.session.id"]', s)
        self.assertIn('name == "anthropic.session.outcome_evaluation"', s)
        self.assertIn('"EVALUATOR"', s)

    def test_content_off_is_allowlist_not_known_key_denylist(self):
        s = statements()
        self.assertIn('keep_keys(attributes,', s)
        self.assertIn('context: spanevent', RECIPE)
        self.assertIn('context: resource', RECIPE)
        self.assertIn('keep_keys(attributes, ["service.name", "project_name", "project_type"])', s)
        self.assertIn('delete_matching_keys(attributes, ".*")', s)
        self.assertIn('"gen_ai.usage.input_tokens"', s)
        self.assertIn('"anthropic.session.id"', s)
        self.assertIn('"anthropic.session.outcome_evaluation.result"', s)

    def test_full_content_batch_is_bounded_by_span_count(self):
        batch = CFG["processors"]["batch"]
        self.assertLessEqual(batch["send_batch_max_size"], 1)
        self.assertEqual(batch["send_batch_size"], batch["send_batch_max_size"])
        self.assertIn("single span", TEXT.lower())

    def test_receiver_claims_do_not_assume_gzip_is_unsupported(self):
        self.assertNotIn("receiver rejects gzip", TEXT)
        self.assertNotIn("receiver rejects gzip", RECIPE)
        self.assertNotIn("a gzip body is rejected with 400", TEXT)

    def test_every_documented_content_key_is_gated_off_by_default(self):
        s = statements()
        allowed = re.search(r'keep_keys\(attributes, \[([^\]]+)\]\) where[^\n]*!= "true"', s)
        self.assertIsNotNone(allowed)
        for key in CONTENT_KEYS + ["gen_ai.input.messages.0", "gen_ai.output.messages.payload"]:
            self.assertNotIn(f'"{key}"', allowed.group(1), key)
        self.assertIn('set(status.message, "error") where status.message != ""', s)

    def test_content_to_panes_only_when_enabled(self):
        for line in statements().splitlines():
            if line.startswith("- set(attributes[\"input.value\"]") or line.startswith("- set(attributes[\"output.value\"]"):
                self.assertIn('== "true"', line)


class Fixture(unittest.TestCase):
    def test_metadata_payload_has_no_content_keys(self):
        req, _ = build("metadata_only", "MARK")
        keys = {a.key for sp in req.resource_spans[0].scope_spans[0].spans for a in sp.attributes}
        self.assertFalse(keys & set(CONTENT_KEYS))
        self.assertIn("gen_ai.usage.input_tokens", keys)

    def test_content_payload_carries_marker(self):
        req, _ = build("content", "MARK")
        blob = req.SerializeToString()
        self.assertIn(b"MARK", blob)


if __name__ == "__main__":
    unittest.main()
