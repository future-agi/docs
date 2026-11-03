"""Checks for run_e2e.sh against a fake `openclaw` (stdlib only, no network).

    python3 -m unittest discover -s tests -t .

The fake records every call with its OPENCLAW_HOME and prints the version it is
told to. The real end-to-end run is run_e2e.sh itself.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / "run_e2e.sh"
PATCH = HERE / "futureagi.patch.json5"
PAGE = HERE.parents[2] / "src/pages/docs/integrations/coding-agents/openclaw.mdx"
PLUGIN = "clawhub:@openclaw/diagnostics-otel"

FAKE_OPENCLAW = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    with open(os.environ["FAKE_OPENCLAW_LOG"], "a") as log:
        log.write(json.dumps({"argv": sys.argv[1:], "home": os.environ.get("OPENCLAW_HOME")}) + "\\n")
    if sys.argv[1:] == ["--version"]:
        print("OpenClaw " + os.environ["FAKE_OPENCLAW_VERSION"] + " (abc1234)")
    """
)


class RunE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = self.tmp / "openclaw"
        self.bin.write_text(FAKE_OPENCLAW)
        self.bin.chmod(0o755)
        self.log = self.tmp / "calls.jsonl"

    def run_script(self, version, **env):
        full = {
            "PATH": os.environ["PATH"],
            "FI_API_KEY": "test-api-key",
            "FI_SECRET_KEY": "test-secret-key",
            "MODEL_BASE_URL": "http://127.0.0.1:9/v1",
            "MODEL_API_KEY": "test-model-key",
            "MODEL_ID": "test-model",
            "OPENCLAW_BIN": str(self.bin),
            "FAKE_OPENCLAW_LOG": str(self.log),
            "FAKE_OPENCLAW_VERSION": version,
            "TMPDIR": str(self.tmp),
        }
        full.update(env)
        result = subprocess.run(
            ["bash", str(SCRIPT)], env=full, capture_output=True, text=True, timeout=60
        )
        calls = []
        if self.log.exists():
            calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, calls

    @staticmethod
    def installs(calls):
        return [c["argv"][2] for c in calls if c["argv"][:2] == ["plugins", "install"]]

    def test_plugin_is_pinned_to_the_openclaw_version(self):
        for version in ("2026.10.5", "2026.10.10", "2026.10.10-beta.1", "2027.1.2"):
            with self.subTest(version=version):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_script(version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.installs(calls), [f"{PLUGIN}@{version}"])
                self.assertTrue(any(c["argv"][:2] == ["agent", "--local"] for c in calls))

    def test_explicit_plugin_version(self):
        result, calls = self.run_script("2026.10.10", DIAGNOSTICS_OTEL_VERSION="2026.10.5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installs(calls), [f"{PLUGIN}@2026.10.5"])

    def test_rejects_openclaw_older_than_the_minimum(self):
        for version in ("2026.10.3", "2026.10.4", "2026.10.5-beta.4", "2026.9.33"):
            with self.subTest(version=version):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_script(version)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("needs OpenClaw 2026.10.5 or later", result.stderr)
                self.assertEqual(self.installs(calls), [])

    def test_rejects_plugin_newer_than_openclaw(self):
        # The failure the recipe hit: diagnostics-otel X requires plugin API >= X.
        result, calls = self.run_script("2026.10.5", DIAGNOSTICS_OTEL_VERSION="2026.10.10-beta.1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs OpenClaw 2026.10.10-beta.1 or later", result.stderr)
        self.assertEqual(self.installs(calls), [])

    def test_rejects_unreadable_version(self):
        result, calls = self.run_script("unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not read the OpenClaw version", result.stderr)
        self.assertEqual(self.installs(calls), [])

    def test_openclaw_home_is_a_resolved_path(self):
        # macOS mktemp returns /var/folders/... (/var -> /private/var). OpenClaw
        # skips its bundled plugin skills when OPENCLAW_HOME is under a symlink.
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "link"
        link.symlink_to(real, target_is_directory=True)
        env = {"PATH": os.environ["PATH"], "TMPDIR": str(link)}
        # Precondition: here mktemp returns a path through a symlink (TMPDIR on
        # Linux; macOS mktemp uses /var/folders whatever TMPDIR says).
        raw = subprocess.run(["mktemp", "-d"], env=env, capture_output=True, text=True).stdout.strip()
        os.rmdir(raw)
        self.assertNotEqual(raw, os.path.realpath(raw))
        result, calls = self.run_script("2026.10.5", TMPDIR=str(link))
        self.assertEqual(result.returncode, 0, result.stderr)
        homes = {c["home"] for c in calls}
        self.assertEqual(len(homes), 1)
        home = homes.pop()
        self.assertEqual(home, os.path.realpath(home))
        self.assertFalse(os.path.exists(home), "the temporary OPENCLAW_HOME is removed on exit")


class VersionPinsAgreeTest(unittest.TestCase):
    def test_page_and_patch_pin_the_tested_version(self):
        minimum = re.search(r'^MIN_OPENCLAW_VERSION="([^"]+)"', SCRIPT.read_text(), re.M)[1]
        pinned = f"openclaw plugins install {PLUGIN}@{minimum}"
        self.assertIn(pinned, PATCH.read_text())
        page = PAGE.read_text()
        self.assertIn(pinned, page)
        self.assertIn(f"OpenClaw {minimum} or later", page)
        # No unpinned install command left on the page or in the patch.
        unpinned = re.compile(r"plugins install " + re.escape(PLUGIN) + r"(?![@\w])")
        self.assertIsNone(unpinned.search(page))
        self.assertIsNone(unpinned.search(PATCH.read_text()))


if __name__ == "__main__":
    unittest.main()
