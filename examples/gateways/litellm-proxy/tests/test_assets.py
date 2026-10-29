"""The shipped config files and the docs page keep the promises the PRD makes (stdlib only)."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "gateways" / "litellm-proxy.mdx"


def read(name: str) -> str:
    return (ROOT / name).read_text()


def env_example() -> dict[str, str]:
    out = {}
    for line in read("env.example").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out


class ProxyConfigTest(unittest.TestCase):
    def test_config_enables_only_the_otel_callback(self):
        text = read("config.yaml")
        self.assertIn('callbacks: ["otel"]', text)
        for other in ("langfuse", "langsmith", "success_callback", "failure_callback"):  # AC-05
            self.assertNotIn(other, text.lower())

    def test_config_holds_no_secret(self):
        text = read("config.yaml")
        self.assertNotRegex(text, r"sk-[A-Za-z0-9]{8,}")
        self.assertIn("os.environ/LITELLM_MASTER_KEY", text)


class EnvExampleTest(unittest.TestCase):
    def test_both_key_headers_no_bearer_and_no_spaces(self):
        env = env_example()
        headers = env["OTEL_HEADERS"]
        self.assertRegex(headers, r"^X-Api-Key=[^,\s]+,X-Secret-Key=[^,\s]+$")
        self.assertNotIn("Bearer", read("env.example").split("OTEL_HEADERS")[1].splitlines()[0])

    def test_project_name_endpoint_and_content_default(self):
        env = env_example()
        self.assertIn("project_name=", env["OTEL_RESOURCE_ATTRIBUTES"])
        self.assertEqual(env["OTEL_EXPORTER"], "otlp_http")
        self.assertTrue(env["OTEL_ENDPOINT"].endswith("/v1/traces"))
        self.assertEqual(env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"], "NO_CONTENT")
        self.assertEqual(env["LITELLM_OTEL_V2"], "true")

    def test_metrics_events_and_compression_stay_off(self):
        text = read("env.example")
        for name in ("LITELLM_OTEL_INTEGRATION_ENABLE_METRICS", "LITELLM_OTEL_INTEGRATION_ENABLE_EVENTS", "OTEL_EXPORTER_OTLP_COMPRESSION"):
            self.assertNotRegex(text, rf"(?m)^{name}=")

    def test_requirements_pin_the_tested_version_and_the_otel_packages(self):
        text = read("requirements.txt")
        self.assertIn("litellm[proxy]==1.105.1", text)
        for pkg in ("opentelemetry-sdk==", "opentelemetry-exporter-otlp==", "opentelemetry-instrumentation-fastapi=="):
            self.assertIn(pkg, text)


class ScrubCollectorTest(unittest.TestCase):
    """Future AGI's collector serves traces only and rejects compressed bodies (BRIEF DoD 6)."""

    def setUp(self):
        self.text = read("collector/otelcol-scrub.yaml")
        self.code = "\n".join(l for l in self.text.splitlines() if not l.lstrip().startswith("#"))

    def test_collector_metrics_off_and_compression_none(self):
        self.assertRegex(self.code, r"(?s)telemetry:\s+metrics:\s+level: none")
        self.assertRegex(self.code, r"(?m)^\s+compression: none$")

    def test_only_a_traces_pipeline_exists(self):
        pipelines = self.code.split("pipelines:")[1]
        self.assertRegex(pipelines, r"(?m)^\s+traces:$")
        self.assertNotRegex(pipelines, r"(?m)^\s+(metrics|logs):$")

    def test_keys_come_from_the_environment(self):
        self.assertIn("${env:FI_API_KEY}", self.code)
        self.assertIn("${env:FI_SECRET_KEY}", self.code)
        self.assertNotRegex(self.code, r"sk-[A-Za-z0-9]{8,}")

    def test_it_deletes_what_the_contract_calls_leaky_on_v2(self):
        import otlp_contract as oc

        v2_attrs = [k for k in oc.LEAKY_ATTRS if not k.startswith(("metadata.", "hidden_params"))]
        for key in v2_attrs + list(oc.LEAKY_EVENT_ATTRS):
            self.assertIn(f'delete_key(attributes, "{key}")', self.code, key)


class ScriptsTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash"), "bash not available")
    def test_run_e2e_parses(self):
        done = subprocess.run(["bash", "-n", str(ROOT / "run_e2e.sh")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    @unittest.skipUnless(shutil.which("bash"), "bash not available")
    def test_run_e2e_help_lists_the_settings(self):
        done = subprocess.run(["bash", str(ROOT / "run_e2e.sh"), "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        for word in ("RUNNER", "MODE", "CONTENT", "TARGET", "FI_PROJECT_NAME", "COLLECTOR"):
            self.assertIn(word, done.stdout)


@unittest.skipUnless(PAGE.exists(), "docs page not in this checkout")
class PageTest(unittest.TestCase):
    def setUp(self):
        self.text = PAGE.read_text()

    def test_it_says_proxy_and_links_the_sdk_package(self):  # AC-01 / R-01
        self.assertIn("Proxy", self.text.split("---", 2)[1])
        self.assertIn("(/docs/integrations/traceai/litellm)", self.text)
        self.assertNotRegex(self.text, r"(?m)^\s*(pip|uv pip) install[^\n]*traceAI-litellm")

    def test_style_guide_basics(self):
        self.assertTrue(self.text.split("---", 2)[2].lstrip().startswith("## About"))
        self.assertNotIn("—", self.text)  # no em-dashes
        self.assertFalse("PLACEHOLDER" in self.text, "a placeholder is left in the page")

    def test_every_env_var_in_the_page_snippet_is_in_env_example(self):
        env = env_example()
        block = re.search(r"```bash\nLITELLM_OTEL_V2=true\n(.*?)```", self.text, re.S).group(1)
        for line in block.splitlines():
            if "=" in line:
                self.assertIn(line.split("=", 1)[0], env)

    def test_the_page_names_the_tested_version(self):
        self.assertIn("1.105.1", self.text)


if __name__ == "__main__":
    unittest.main()
