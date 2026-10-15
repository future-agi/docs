"""The shipped Antigravity hooks.json commands must never break the agent loop, with or without the emitter.

Antigravity IDE 2.5.5 runs a hook command with ``sh -c`` on Unix (``cmd /c`` on
Windows), in the folder that contains hooks.json, with the JSON payload on stdin,
and reads a JSON decision from stdout (embedded hooks reference in the 2.5.5
language server). Hooks run synchronously and block the agent loop. Every shipped
command is the canonical subshell guard
``(python3 -B <emit.py> antigravity <Event> 2>/dev/null || true)``: exit 0 and no
output however the emitter or python3 fails, and the payload reaches python3
whether it comes on stdin or as a trailing heredoc (some hosts use one).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import FIXTURES, Receiver, attrs, load_jsonl

EXAMPLE = Path(__file__).resolve().parents[2] / "google-antigravity"
PERMISSION_HOOKS = {"PreToolUse"}
EVENTS = ["SessionStart", "PreInvocation", "PostInvocation", "PostToolUse", "Stop"]
CONFIGS = {"hooks.json": "fi-hook-to-otlp/emit.py",
           "hooks.user.json": '"$HOME/.gemini/config/fi-hook-to-otlp/emit.py"'}
EXPECTED_STDOUT = {"Stop": {"decision": ""}}
TRANSPORTS = ("stdin", "heredoc")
SHELLS = [sh for sh in ("/bin/sh", "/bin/zsh", "/bin/bash", "/bin/dash") if os.path.exists(sh)]
PROMPT = "it's $HOME `id` \"quoted\" PROMPT_MARK"


def entry(config_name):
    return json.loads((EXAMPLE / config_name).read_text())["fi-hook-to-otlp"]


def commands(config_name):
    out = []
    for event, items in entry(config_name).items():
        for item in items:
            for hook in item.get("hooks", [item]):
                out.append((event, hook["command"]))
    return out


def run_hook(command, cwd, payload, env, shell="/bin/sh", transport="stdin"):
    text = json.dumps(payload)
    if transport == "stdin":
        return subprocess.run([shell, "-c", command], cwd=cwd, input=text,
                              capture_output=True, text=True, env=env, timeout=30)
    script = f"{command} <<'AG_HOOK_EOF'\n{text}\nAG_HOOK_EOF"
    return subprocess.run([shell, "-c", script], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, env=env, timeout=30)


def session(conversation_id):
    """The fixture conversation (registered events only), with its own id and a quoting-hostile prompt."""
    records = []
    for record in load_jsonl(FIXTURES / "antigravity" / "session.jsonl"):
        payload = json.loads(json.dumps(record["payload"]).replace("fixture-ag-conv-0001", conversation_id))
        if "lastUserInput" in payload:
            payload["lastUserInput"] = PROMPT
        records.append((record["event"], payload))
    return records


def base_env(home=None, **extra):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home or tempfile.gettempdir()}
    env.update(extra)
    return env


class AntigravityHooksConfigTest(unittest.TestCase):
    def test_observe_only_and_every_command_is_the_guarded_subshell(self):
        for name, path in CONFIGS.items():
            self.assertEqual(list(entry(name)), EVENTS, name)
            self.assertFalse(PERMISSION_HOOKS & set(entry(name)), name)
            self.assertEqual(entry(name)["PostToolUse"][0]["matcher"], "*")
            for event, command in commands(name):
                self.assertEqual(command, f"(python3 -B {path} antigravity {event} 2>/dev/null || true)", name)

    def test_page_snippet_matches_the_shipped_commands(self):
        page = (EXAMPLE.parents[2] / "src/pages/docs/integrations/coding-agents/google-antigravity.mdx").read_text()
        for _, command in commands("hooks.json"):
            self.assertIn(command, page)
        self.assertNotIn("antigravity PreToolUse", page)
        self.assertNotIn("|| true\"", page)

    def test_missing_emitter_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for name in CONFIGS:
                        for event, command in commands(name):
                            result = run_hook(command, empty, {"conversationId": "cfg"}, base_env(empty),
                                              shell, transport)
                            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""),
                                             f"{shell} {transport} {name} {event}")

    def test_missing_python_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for event, command in commands("hooks.json"):
                        result = run_hook(command, empty, {"conversationId": "cfg"}, base_env(PATH=empty),
                                          shell, transport)
                        self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {transport} {event}")

    def run_installed(self, name, install_args, hooks_dir_of, shells):
        """Install, then replay the fixture through the installed commands per shell and transport."""
        results = {}
        with tempfile.TemporaryDirectory() as tmp:
            home, project = Path(tmp, "home"), Path(tmp, "project")
            home.mkdir()
            project.mkdir()
            subprocess.run([str(EXAMPLE / "install.sh"), *install_args(project)], check=True,
                           capture_output=True, env=base_env(str(home)))
            hooks_dir = hooks_dir_of(project, home)
            installed = dict(commands(name))
            self.assertEqual(json.loads((hooks_dir / "hooks.json").read_text()),
                             json.loads((EXAMPLE / name).read_text()))
            for shell in shells:
                for transport in TRANSPORTS:
                    rx = Receiver()
                    try:
                        env = base_env(str(home), FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                       FI_HOOK_CAPTURE_CONTENT="1", FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces",
                                       FI_HOOK_STATE_DIR=str(Path(tmp, f"state-{Path(shell).name}-{transport}")))
                        conv = f"cfg-{Path(shell).name}-{transport}"
                        for event, payload in session(conv):
                            result = run_hook(installed[event], hooks_dir, payload, env, shell, transport)
                            label = f"{name} {shell} {transport} {event}"
                            self.assertEqual(result.returncode, 0, label)
                            self.assertEqual(json.loads(result.stdout), EXPECTED_STDOUT.get(event, {}), label)
                        results[(shell, transport)] = (conv, rx.spans())
                    finally:
                        rx.close()
            self.assertEqual(list(project.rglob("__pycache__")) + list(home.rglob("__pycache__")), [],
                             "-B keeps bytecode out of the repo")
        return results

    def assert_payload_arrived(self, results):
        for (shell, transport), (conv, spans) in results.items():
            label = f"{shell} {transport}"
            tools = [s for s in spans if s["name"] == "list_dir"]
            self.assertTrue(tools, f"{label}: the payload reached the emitter")
            self.assertEqual(attrs(tools[-1])["session.id"], conv, label)
            turn = [s for s in spans if s["name"] == "Antigravity turn"][-1]
            # The heredoc is quoted: no expansion of $HOME, backticks or quotes on the way in.
            self.assertEqual(attrs(turn)["input.value"], PROMPT, label)

    def test_installed_workspace_hooks_receive_the_payload_on_stdin_and_as_heredoc(self):
        results = self.run_installed("hooks.json", lambda project: [str(project)],
                                     lambda project, home: project / ".agents", SHELLS)
        self.assertEqual(len(results), len(SHELLS) * len(TRANSPORTS))
        self.assert_payload_arrived(results)

    def test_installed_user_hooks_receive_the_payload_on_stdin_and_as_heredoc(self):
        results = self.run_installed("hooks.user.json", lambda project: ["--user"],
                                     lambda project, home: home / ".gemini" / "config", SHELLS[:1])
        self.assert_payload_arrived(results)

    def test_user_hooks_do_not_depend_on_the_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            subprocess.run([str(EXAMPLE / "install.sh"), "--user"], check=True, capture_output=True,
                           env=base_env(str(home)))
            rx = Receiver()
            try:
                env = base_env(str(home), FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                               FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces", FI_HOOK_STATE_DIR=str(home / "state"))
                command = dict(commands("hooks.user.json"))["PostToolUse"]
                event, payload = session("cwd-check")[3]
                self.assertEqual(event, "PostToolUse")
                with tempfile.TemporaryDirectory() as elsewhere:
                    result = run_hook(command, elsewhere, payload, env)
                self.assertEqual((result.returncode, json.loads(result.stdout)), (0, {}))
                self.assertTrue(any(s["name"] == "list_dir" for s in rx.spans()))
            finally:
                rx.close()

    def test_unparenthesized_guard_would_lose_a_heredoc_payload(self):
        rx = Receiver()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp, "project")
                project.mkdir()
                subprocess.run([str(EXAMPLE / "install.sh"), str(project)], check=True, capture_output=True,
                               env=base_env(tmp))
                env = base_env(FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                               FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces", FI_HOOK_STATE_DIR=str(Path(tmp, "state")))
                command = dict(commands("hooks.json"))["PostToolUse"]
                bare = re.fullmatch(r"\((.*)\)", command).group(1)
                _, payload = session("bare")[3]
                run_hook(bare, project / ".agents", payload, env, transport="heredoc")
                self.assertEqual(rx.spans(), [])
                run_hook(command, project / ".agents", payload, env, transport="heredoc")
                self.assertTrue(any(s["name"] == "list_dir" for s in rx.spans()))
        finally:
            rx.close()


class AntigravityInstallerTest(unittest.TestCase):
    def test_existing_hooks_file_is_kept_and_only_the_entry_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, home = Path(tmp, "project"), Path(tmp, "home")
            (project / ".agents").mkdir(parents=True)
            home.mkdir()
            mine = {"lint-checker": {"PostToolUse": [{"matcher": "run_command", "hooks": [{"command": "./lint.sh"}]}]}}
            (project / ".agents" / "hooks.json").write_text(json.dumps(mine))
            result = subprocess.run([str(EXAMPLE / "install.sh"), str(project)], capture_output=True, text=True,
                                    env=base_env(str(home)))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((project / ".agents" / "hooks.json").read_text()), mine)
            printed = result.stdout[result.stdout.index('"fi-hook-to-otlp"'):result.stdout.rindex("}") + 1]
            self.assertEqual(json.loads("{" + printed + "}"), {"fi-hook-to-otlp": entry("hooks.json")})


if __name__ == "__main__":
    unittest.main()
