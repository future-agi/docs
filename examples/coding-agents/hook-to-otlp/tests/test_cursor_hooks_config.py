"""The shipped Cursor hooks.json must never block Cursor (exit 2 blocks), with or without the emitter."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import Receiver

EXAMPLE = Path(__file__).resolve().parents[2] / "cursor"
PERMISSION_HOOKS = {"preToolUse", "beforeShellExecution", "beforeMCPExecution", "beforeReadFile",
                    "beforeTabFileRead", "subagentStart"}
EXPECTED_STDOUT = {"beforeSubmitPrompt": {"continue": True}}


def commands(config_name):
    config = json.loads((EXAMPLE / config_name).read_text())
    return [(event, hook["command"]) for event, hooks in config["hooks"].items() for hook in hooks]


# Cursor 3.24.18 runs a hook command as `$SHELL -c "<command>"` (falling back to /bin/sh).
SHELLS = [sh for sh in ("/bin/sh", "/bin/zsh", "/bin/bash") if os.path.exists(sh)]


def run_hook(command, cwd, payload, env, shell="/bin/sh"):
    return subprocess.run([shell, "-c", command], cwd=cwd, input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=30)


class HooksConfigTest(unittest.TestCase):
    payload = {"conversation_id": "cfg-1", "generation_id": "g1", "tool_name": "Shell",
               "tool_use_id": "t1", "duration": 5, "status": "completed"}

    def base_env(self, **extra):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir()}
        env.update(extra)
        return env

    def test_observation_hooks_only_and_every_command_guarded(self):
        for name in ("hooks.json", "hooks.user.json"):
            for event, command in commands(name):
                self.assertNotIn(event, PERMISSION_HOOKS, f"{name}: {event}")
                self.assertTrue(command.startswith("python3 -B "), command)
                self.assertTrue(command.endswith(" 2>/dev/null || true"), command)

    def test_missing_emitter_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for name in ("hooks.json", "hooks.user.json"):
                    for event, command in commands(name):
                        result = run_hook(command, empty, {**self.payload, "hook_event_name": event},
                                          self.base_env(), shell)
                        self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {name} {event}")

    def test_missing_python_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for event, command in commands("hooks.json"):
                    result = run_hook(command, empty, self.payload, self.base_env(PATH=empty), shell)
                    self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {event}")

    def test_installed_hooks_answer_cursor_and_export(self):
        rx = Receiver()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp, "project")
                project.mkdir()
                subprocess.run([str(EXAMPLE / "install.sh"), str(project)], check=True, capture_output=True)
                env = self.base_env(FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                    FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces",
                                    FI_HOOK_STATE_DIR=str(Path(tmp, "state")))
                for event, command in commands("hooks.json"):
                    result = run_hook(command, project, {**self.payload, "hook_event_name": event}, env)
                    self.assertEqual(result.returncode, 0, event)
                    self.assertEqual(json.loads(result.stdout), EXPECTED_STDOUT.get(event, {}), event)
                self.assertTrue(any(s["name"] == "Shell" for s in rx.spans()))
                self.assertEqual(list(project.rglob("__pycache__")), [], "-B keeps bytecode out of the repo")
        finally:
            rx.close()


if __name__ == "__main__":
    unittest.main()
