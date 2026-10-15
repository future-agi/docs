"""The shipped Devin Desktop hooks.json, run the way Cascade runs it.

Cascade runs a hook's ``command`` with ``bash -c`` and passes the event JSON on
stdin (https://docs.devin.ai/desktop/cascade/hooks, Configuration Options). It
treats exit code 2 from a pre-hook as "block" (pre_user_prompt blocks the
prompt). Every shipped command must exit 0 with empty stdout, also when the
emitter or python3 is missing.

Each command is also run with the payload as a trailing heredoc
(``<command> <<'EOF'``), the transport some hook hosts use: the subshell guard
``( ... || true)`` keeps the heredoc on the emitter instead of on ``true``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, Receiver

APP_DIR = ROOT.parent / "devin-desktop"
HOOKS = json.loads((APP_DIR / "hooks.json").read_text(encoding="utf-8"))["hooks"]
EXPECTED = {"pre_user_prompt", "post_read_code", "post_write_code", "post_run_command",
            "post_mcp_tool_use", "post_cascade_response"}
# Cascade uses bash; /bin/sh is the POSIX baseline.
SHELLS = [sh for sh in ("/bin/sh", shutil.which("bash") or "/bin/bash") if os.path.exists(sh)]
TRANSPORTS = ("stdin", "heredoc")
# Span each hook exports once the emitter is installed.
SPAN_FOR = {"pre_user_prompt": None, "post_read_code": "read_code", "post_write_code": "write_code",
            "post_run_command": "run_command", "post_mcp_tool_use": "list_commits",
            "post_cascade_response": "Cascade turn"}


def payload(event: str, trajectory: str = "cfg-traj") -> str:
    info = {"file_path": "/tmp/x", "edits": [], "command_line": "ls", "mcp_server_name": "github",
            "mcp_tool_name": "list_commits", "user_prompt": "p", "response": "r"}
    return json.dumps({"agent_action_name": event, "trajectory_id": trajectory, "execution_id": "cfg-exec",
                       "model_name": "Claude Sonnet 4", "tool_info": info})


def run(command: str, shell: str, transport: str, home: str, stdin: str, **env: str) -> subprocess.CompletedProcess:
    full = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home}
    full.update(env)
    if transport == "heredoc":
        script, stdin = f"{command} <<'HOOK_EOF'\n{stdin}\nHOOK_EOF\n", ""
    else:
        script = command
    return subprocess.run([shell, "-c", script], input=stdin, capture_output=True, text=True,
                          env=full, cwd=home, timeout=30)


class DevinDesktopHooksConfigTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_registered_hooks_are_guarded(self):
        self.assertEqual(set(HOOKS), EXPECTED)
        self.assertNotIn("post_cascade_response_with_transcript", HOOKS)
        for event, entries in HOOKS.items():
            self.assertEqual(len(entries), 1, event)
            entry = entries[0]
            self.assertIs(entry["show_output"], False, event)
            self.assertTrue(entry["command"].startswith("(python3 -B "), event)
            self.assertTrue(entry["command"].endswith(f" devin_desktop {event} 2>/dev/null || true)"), event)

    def test_page_shows_the_shipped_hooks_json(self):
        page = (ROOT.parents[2] / "src/pages/docs/integrations/coding-agents/devin-desktop.mdx").read_text(encoding="utf-8")
        block = page.split("```json\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(json.loads(block)["hooks"], HOOKS)

    def test_missing_emitter_never_blocks(self):
        for shell in SHELLS:
            for transport in TRANSPORTS:
                for event, entries in HOOKS.items():
                    result = run(entries[0]["command"], shell, transport, self.home, payload(event))
                    self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""),
                                     f"{shell} {transport} {event}")

    def test_missing_python_never_blocks(self):
        empty_bin = tempfile.mkdtemp()
        try:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for event, entries in HOOKS.items():
                        result = run(entries[0]["command"], shell, transport, self.home, payload(event),
                                     PATH=empty_bin)
                        self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {transport} {event}")
        finally:
            shutil.rmtree(empty_bin, ignore_errors=True)

    def test_installed_commands_read_the_payload_and_print_nothing(self):
        install = subprocess.run([shutil.which("bash") or "/bin/bash", str(APP_DIR / "install.sh")],
                                 capture_output=True, text=True,
                                 env={"PATH": os.environ.get("PATH", ""), "HOME": self.home}, timeout=30)
        self.assertEqual(install.returncode, 0, install.stderr)
        installed = json.loads(Path(self.home, ".codeium/windsurf/hooks.json").read_text())["hooks"]
        self.assertEqual(installed, HOOKS)
        for shell in SHELLS:
            for transport in TRANSPORTS:
                receiver = Receiver()
                trajectory = f"cfg-{Path(shell).name}-{transport}"
                try:
                    for event in HOOKS:
                        before = len(receiver.requests)
                        result = run(HOOKS[event][0]["command"], shell, transport, self.home,
                                     payload(event, trajectory),
                                     FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                     FI_OTLP_ENDPOINT=f"{receiver.url}/v1/traces",
                                     FI_HOOK_STATE_DIR=os.path.join(self.home, "state"))
                        label = f"{shell} {transport} {event}"
                        self.assertEqual((result.returncode, result.stdout), (0, ""), label)
                        expected = SPAN_FOR[event]
                        if expected is None:  # the turn start exports nothing yet
                            self.assertEqual(len(receiver.requests), before, label)
                            continue
                        receiver.wait_for(before + 1)
                        names = {s["name"] for _, _, body in receiver.requests[before:]
                                 for rs in body["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]}
                        self.assertIn(expected, names, label)
                finally:
                    receiver.close()
        self.assertEqual(list(Path(self.home).rglob("__pycache__")), [], "-B writes no bytecode")


if __name__ == "__main__":
    unittest.main()
