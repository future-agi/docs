"""The shipped Cursor hooks.json must never block Cursor (exit 2 blocks), with or without the emitter.

Cursor runs a hook command as `$SHELL -c <command>` (falling back to /bin/sh) and passes the
payload in one of two ways, depending on the surface (both read from the Cursor 3.24.18 bundle):

- stdin: the IDE agent pipes the JSON to the command's stdin.
- heredoc: the bundled headless agent host (commandHookPayloadTransport "argv_heredoc") runs
  `<command> <<'CURSOR_HOOK_EOF'\n<json>\nCURSOR_HOOK_EOF` with stdin ignored.

Every shipped command is a subshell, `(python3 -B ... 2>/dev/null || true)`, so the heredoc
reaches python3. Without the parentheses the heredoc binds to `true` and the emitter reads nothing.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import Receiver, attrs

EXAMPLE = Path(__file__).resolve().parents[2] / "cursor"
PERMISSION_HOOKS = {"preToolUse", "beforeShellExecution", "beforeMCPExecution", "beforeReadFile",
                    "beforeTabFileRead", "subagentStart"}
EXPECTED_STDOUT = {"beforeSubmitPrompt": {"continue": True}}
CONFIGS = {"hooks.json": ".cursor/hooks/fi-hook-to-otlp/emit.py", "hooks.user.json": "./hooks/fi-hook-to-otlp/emit.py"}
TRANSPORTS = ("stdin", "heredoc")
SHELLS = [sh for sh in ("/bin/sh", "/bin/zsh", "/bin/bash", "/bin/dash") if os.path.exists(sh)]


def commands(config_name):
    config = json.loads((EXAMPLE / config_name).read_text())
    return [(event, hook["command"]) for event, hooks in config["hooks"].items() for hook in hooks]


def run_hook(command, cwd, payload, env, shell="/bin/sh", transport="stdin"):
    """Run a hook command the way Cursor does for the given payload transport."""
    text = json.dumps(payload)
    if transport == "stdin":
        return subprocess.run([shell, "-c", command], cwd=cwd, input=text,
                              capture_output=True, text=True, env=env, timeout=30)
    script = f"{command} <<'CURSOR_HOOK_EOF'\n{text}\nCURSOR_HOOK_EOF"
    return subprocess.run([shell, "-c", script], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, env=env, timeout=30)


class HooksConfigTest(unittest.TestCase):
    payload = {"conversation_id": "cfg-1", "generation_id": "g1", "tool_name": "Shell",
               "tool_use_id": "t1", "duration": 5, "status": "completed",
               "prompt": "it's $HOME `id` \"quoted\" PROMPT_MARK"}

    def base_env(self, home=None, **extra):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home or tempfile.gettempdir()}
        env.update(extra)
        return env

    def test_observation_hooks_only_and_every_command_is_the_guarded_subshell(self):
        for name, path in CONFIGS.items():
            for event, command in commands(name):
                self.assertNotIn(event, PERMISSION_HOOKS, f"{name}: {event}")
                self.assertEqual(command, f"(python3 -B {path} cursor {event} 2>/dev/null || true)")

    def test_missing_emitter_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for name in CONFIGS:
                        for event, command in commands(name):
                            result = run_hook(command, empty, {**self.payload, "hook_event_name": event},
                                              self.base_env(), shell, transport)
                            self.assertEqual((result.returncode, result.stdout), (0, ""),
                                             f"{shell} {transport} {name} {event}")

    def test_missing_python_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for event, command in commands("hooks.json"):
                        result = run_hook(command, empty, self.payload, self.base_env(PATH=empty), shell, transport)
                        self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {transport} {event}")

    def run_installed(self, name, install_args, cwd_of, shells):
        """Install, then run every shipped command per shell and transport; return spans per run."""
        results = {}
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp, "home")
            project = Path(tmp, "project")
            home.mkdir()
            project.mkdir()
            subprocess.run([str(EXAMPLE / "install.sh"), *install_args(project)], check=True,
                           capture_output=True, env=self.base_env(str(home)))
            for shell in shells:
                for transport in TRANSPORTS:
                    rx = Receiver()
                    try:
                        env = self.base_env(str(home), FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                            FI_HOOK_CAPTURE_CONTENT="1",
                                            FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces",
                                            FI_HOOK_STATE_DIR=str(Path(tmp, f"state-{Path(shell).name}-{transport}")))
                        sid = f"cfg-{Path(shell).name}-{transport}"
                        for event, command in commands(name):
                            result = run_hook(command, cwd_of(project, home),
                                              {**self.payload, "conversation_id": sid, "hook_event_name": event},
                                              env, shell, transport)
                            label = f"{name} {shell} {transport} {event}"
                            self.assertEqual(result.returncode, 0, label)
                            self.assertEqual(json.loads(result.stdout), EXPECTED_STDOUT.get(event, {}), label)
                        results[(shell, transport)] = (sid, rx.spans())
                    finally:
                        rx.close()
            self.assertEqual(list(project.rglob("__pycache__")) + list(home.rglob("__pycache__")), [],
                             "-B keeps bytecode out of the repo")
        return results

    def assert_payload_arrived(self, results):
        for (shell, transport), (sid, spans) in results.items():
            label = f"{shell} {transport}"
            shell_spans = [s for s in spans if s["name"] == "Shell"]
            self.assertTrue(shell_spans, f"{label}: the payload reached the emitter")
            self.assertEqual(attrs(shell_spans[-1])["session.id"], sid, label)
            turn = [s for s in spans if s["name"] == "Cursor turn"][-1]
            # The heredoc is quoted: no expansion of $HOME, backticks or quotes on the way in.
            self.assertEqual(attrs(turn)["input.value"], self.payload["prompt"], label)

    def test_installed_project_hooks_receive_the_payload_on_stdin_and_as_heredoc(self):
        results = self.run_installed("hooks.json", lambda project: [str(project)],
                                     lambda project, home: project, SHELLS)
        self.assertEqual(len(results), len(SHELLS) * len(TRANSPORTS))
        self.assert_payload_arrived(results)

    def test_installed_user_hooks_receive_the_payload_on_stdin_and_as_heredoc(self):
        results = self.run_installed("hooks.user.json", lambda project: ["--user"],
                                     lambda project, home: home / ".cursor", SHELLS[:1])
        self.assert_payload_arrived(results)

    def test_unparenthesized_guard_would_lose_a_heredoc_payload(self):
        # Why the parentheses are required: `cmd || true <<EOF` feeds the heredoc to `true`.
        rx = Receiver()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp, "project")
                project.mkdir()
                subprocess.run([str(EXAMPLE / "install.sh"), str(project)], check=True, capture_output=True)
                env = self.base_env(FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                    FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces",
                                    FI_HOOK_STATE_DIR=str(Path(tmp, "state")))
                command = dict(commands("hooks.json"))["postToolUse"]
                bare = re.fullmatch(r"\((.*)\)", command).group(1)
                run_hook(bare, project, self.payload, env, transport="heredoc")
                self.assertEqual(rx.spans(), [])
                run_hook(command, project, self.payload, env, transport="heredoc")
                self.assertTrue(any(s["name"] == "Shell" for s in rx.spans()))
        finally:
            rx.close()


if __name__ == "__main__":
    unittest.main()
