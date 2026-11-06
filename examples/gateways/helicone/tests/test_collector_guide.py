"""Reader-facing setup checks; run with python3 -I tests/test_docs_contract.py."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[4]
GUIDE = ROOT / "src/pages/docs/integrations/gateways/helicone.mdx"
HELM = ROOT / "src/pages/docs/self-hosting/helm.mdx"
README = ROOT / "examples/gateways/helicone/README.md"


class GuideContract(unittest.TestCase):
    def test_self_hosted_collector_origin_matches_helm(self):
        helm = HELM.read_text()
        guide = GUIDE.read_text()
        forwarded = re.search(r"port-forward svc/futureagi-fi-collector (\d+):\1", helm)
        self.assertIsNotNone(forwarded, "Helm guide must forward the collector")
        self.assertIn(f'FI_BASE_URL="http://localhost:{forwarded.group(1)}"', guide)

    def test_companion_is_customer_how_to_not_test_handoff(self):
        readme = README.read_text()
        for phrase in ("AC-01", "STANDIN", "PASS step", "Step 7", "read-back", "stand-in tests"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, readme)
        self.assertIn("python/run_demo.py", readme)
        self.assertIn("typescript", readme)


if __name__ == "__main__":
    unittest.main()
