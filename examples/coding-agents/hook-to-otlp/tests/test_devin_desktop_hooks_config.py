"""The shipped Devin Desktop hooks.json, run the way Cascade runs it (bash -c).

Cascade treats exit code 2 from a pre-hook as "block" (pre_user_prompt
blocks the prompt). Every shipped command must exit 0 with empty stdout,
also when the emitter or python3 is missing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, Receiver, all_spans

BASH = shutil.which("bash") or "/bin/bash"

APP_DIR = ROOT.parent / "devin-desktop"
HOOKS = json.loads((APP_DIR / "hooks.json").read_text(encoding="utf-8"))["hooks"]
EXPECTED = {"pre_user_prompt", "post_read_code", "post_write_code", "post_run_command",
            "post_mcp_tool_use", "post_cascade_response"}


def payload(event: str) -> str:
    return json.dumps({"agent_action_name": event, "trajectory_id": "cfg-traj", "execution_id": "cfg-exec",
                       "model_name": "Claude Sonnet 4", "tool_info": {"file_path": "/tmp/x"}})


def run(command: str, home: str, stdin: str, **env: str) -> subprocess.CompletedProcess:
    full = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home}
    full.update(env)
    return subprocess.run([BASH, "-c", command], input=stdin, capture_output=True, text=True,
                          env=full, timeout=30)


class DevinDesktopHooksConfigTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_registered_hooks(self):
        self.assertEqual(set(HOOKS), EXPECTED)
        self.assertNotIn("post_cascade_response_with_transcript", HOOKS)
        for event, entries in HOOKS.items():
            self.assertEqual(len(entries), 1, event)
            entry = entries[0]
            self.assertIs(entry["show_output"], False, event)
            self.assertTrue(entry["command"].startswith("python3 -B "), event)
            self.assertTrue(entry["command"].endswith(f" devin_desktop {event} 2>/dev/null || true"), event)

    def test_page_shows_the_shipped_hooks_json(self):
        page = (ROOT.parents[2] / "src/pages/docs/integrations/coding-agents/devin-desktop.mdx").read_text(encoding="utf-8")
        block = page.split("```json\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(json.loads(block)["hooks"], HOOKS)

    def test_missing_emitter_never_blocks(self):
        for event, entries in HOOKS.items():
            result = run(entries[0]["command"], self.home, payload(event))
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""), event)

    def test_missing_python_never_blocks(self):
        empty_bin = tempfile.mkdtemp()
        try:
            for event, entries in HOOKS.items():
                result = run(entries[0]["command"], self.home, payload(event), PATH=empty_bin)
                self.assertEqual((result.returncode, result.stdout), (0, ""), event)
        finally:
            shutil.rmtree(empty_bin, ignore_errors=True)

    def test_installed_commands_export_and_print_nothing(self):
        install = subprocess.run([BASH, str(APP_DIR / "install.sh")], capture_output=True, text=True,
                                 env={"PATH": os.environ.get("PATH", ""), "HOME": self.home}, timeout=30)
        self.assertEqual(install.returncode, 0, install.stderr)
        installed = json.loads(Path(self.home, ".codeium/windsurf/hooks.json").read_text())["hooks"]
        self.assertEqual(installed, HOOKS)
        receiver = Receiver()
        try:
            for event in ("pre_user_prompt", "post_read_code", "post_cascade_response"):
                result = run(HOOKS[event][0]["command"], self.home, payload(event),
                             FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                             FI_OTLP_ENDPOINT=f"{receiver.url}/v1/traces",
                             FI_HOOK_STATE_DIR=os.path.join(self.home, "state"))
                self.assertEqual((result.returncode, result.stdout), (0, ""), event)
            receiver.wait_for(2)
            names = {s["name"] for _, _, body in receiver.requests for s in all_spans(body)}
            self.assertEqual(names, {"read_code", "Cascade turn", "Cascade session"})
        finally:
            receiver.close()


if __name__ == "__main__":
    unittest.main()
