"""The shipped Kiro IDE hook files must never block Kiro, with or without the emitter.

Kiro IDE 1.2.37 runs a v2 command hook with Node's ``spawn(command, {shell: true})``
(``/bin/sh -c`` on macOS and Linux), cwd = the first workspace folder, and writes
the JSON payload to the command's stdin. Exit 2 on UserPromptSubmit / PreToolUse /
PreTaskExec blocks the action, exit 1 on Stop asks the agent to keep working, and
exit-0 stdout on SessionStart / UserPromptSubmit is added to the agent context. So every shipped command is the canonical subshell guard,
``(python3 -B <emit.py> kiro_ide <Trigger> 2>/dev/null || true)``: exit 0 and no
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

from tests.helpers import Receiver, attrs

EXAMPLE = Path(__file__).resolve().parents[2] / "kiro-ide"
GATING = {"PreToolUse", "PreTaskExec"}
CONFIGS = {"fi-hook-to-otlp.json": ".kiro/fi-hook-to-otlp/emit.py",
           "fi-hook-to-otlp.user.json": '"$HOME/.kiro/fi-hook-to-otlp/emit.py"'}
TRANSPORTS = ("stdin", "heredoc")
SHELLS = [sh for sh in ("/bin/sh", "/bin/zsh", "/bin/bash", "/bin/dash") if os.path.exists(sh)]


def commands(config_name):
    doc = json.loads((EXAMPLE / config_name).read_text())
    return [(hook["trigger"], hook["action"]["command"]) for hook in doc["hooks"]]


def run_hook(command, cwd, payload, env, shell="/bin/sh", transport="stdin"):
    text = json.dumps(payload)
    if transport == "stdin":
        return subprocess.run([shell, "-c", command], cwd=cwd, input=text,
                              capture_output=True, text=True, env=env, timeout=30)
    script = f"{command} <<'KIRO_HOOK_EOF'\n{text}\nKIRO_HOOK_EOF"
    return subprocess.run([shell, "-c", script], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, env=env, timeout=30)


def payload_for(trigger, sid):
    payload = {"session_id": sid, "hook_event_name": trigger, "cwd": "/Users/someone/project"}
    if trigger == "UserPromptSubmit":
        payload["prompt"] = "it's $HOME `id` \"quoted\" PROMPT_MARK"
    if trigger == "PostToolUse":
        payload.update(tool_name="read_file", tool_input={"path": "README.md"},
                       tool_response={"success": True, "result": ["ok"]})
    if trigger == "PostTaskExec":
        payload.update(spec_name="auth", task_name="1. Login", task_success=True)
    if trigger.startswith("PostFile"):
        payload["file_path"] = "/Users/someone/project/a.md"
    return payload


class KiroIdeHooksConfigTest(unittest.TestCase):
    def base_env(self, home=None, **extra):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home or tempfile.gettempdir()}
        env.update(extra)
        return env

    def test_observe_only_and_every_command_is_the_guarded_subshell(self):
        for name, path in CONFIGS.items():
            doc = json.loads((EXAMPLE / name).read_text())
            triggers = [hook["trigger"] for hook in doc["hooks"]]
            self.assertEqual(len(triggers), len(set(triggers)), name)
            for hook in doc["hooks"]:
                trigger = hook["trigger"]
                self.assertNotIn(trigger, GATING, f"{name}: {trigger}")
                self.assertEqual(hook["action"]["command"],
                                 f"(python3 -B {path} kiro_ide {trigger} 2>/dev/null || true)", name)
                if trigger in ("PreToolUse", "PostToolUse"):
                    self.assertEqual(hook.get("matcher"), ".*", name)

    def test_page_snippet_matches_the_shipped_command(self):
        page = (EXAMPLE.parents[2] / "src/pages/docs/integrations/coding-agents/kiro-ide.mdx").read_text()
        self.assertIn(dict(commands("fi-hook-to-otlp.json"))["PostToolUse"].replace('"', '\\"'), page)
        self.assertNotIn("emit.py kiro_ide ||", page)

    def test_missing_emitter_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for name in CONFIGS:
                        for trigger, command in commands(name):
                            result = run_hook(command, empty, payload_for(trigger, "cfg"),
                                              self.base_env(empty), shell, transport)
                            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""),
                                             f"{shell} {transport} {name} {trigger}")

    def test_missing_python_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for trigger, command in commands("fi-hook-to-otlp.json"):
                        result = run_hook(command, empty, payload_for(trigger, "cfg"),
                                          self.base_env(PATH=empty), shell, transport)
                        self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {transport} {trigger}")

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
                        for trigger, command in commands(name):
                            result = run_hook(command, cwd_of(project, home), payload_for(trigger, sid),
                                              env, shell, transport)
                            label = f"{name} {shell} {transport} {trigger}"
                            self.assertEqual((result.returncode, result.stdout), (0, ""), label)
                        results[(shell, transport)] = (sid, rx.spans())
                    finally:
                        rx.close()
            self.assertEqual(list(project.rglob("__pycache__")) + list(home.rglob("__pycache__")), [],
                             "-B keeps bytecode out of the repo")
        return results

    def assert_payload_arrived(self, results):
        for (shell, transport), (sid, spans) in results.items():
            label = f"{shell} {transport}"
            tools = [s for s in spans if s["name"] == "read_file"]
            self.assertTrue(tools, f"{label}: the payload reached the emitter")
            self.assertEqual(attrs(tools[-1])["session.id"], sid, label)
            turn = [s for s in spans if s["name"] == "Kiro IDE turn"][-1]
            # The heredoc is quoted: no expansion of $HOME, backticks or quotes on the way in.
            self.assertEqual(attrs(turn)["input.value"], payload_for("UserPromptSubmit", sid)["prompt"], label)
            self.assertEqual(attrs(turn)["coding_agent.hook.event"], "Stop", label)

    def test_installed_project_hooks_receive_the_payload_on_stdin_and_as_heredoc(self):
        results = self.run_installed("fi-hook-to-otlp.json", lambda project: [str(project)],
                                     lambda project, home: project, SHELLS)
        self.assertEqual(len(results), len(SHELLS) * len(TRANSPORTS))
        self.assert_payload_arrived(results)

    def test_installed_user_hooks_receive_the_payload_on_stdin_and_as_heredoc(self):
        # Global hooks run with cwd = the workspace, which has no emitter copy.
        with tempfile.TemporaryDirectory() as workspace:
            results = self.run_installed("fi-hook-to-otlp.user.json", lambda project: ["--user"],
                                         lambda project, home: workspace, SHELLS[:1])
        self.assert_payload_arrived(results)

    def test_unparenthesized_guard_would_lose_a_heredoc_payload(self):
        # Why the parentheses are required: `cmd || true <<EOF` feeds the heredoc to `true`.
        rx = Receiver()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp, "project")
                project.mkdir()
                subprocess.run([str(EXAMPLE / "install.sh"), str(project)], check=True, capture_output=True,
                               env=self.base_env(str(Path(tmp))))
                env = self.base_env(FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                    FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces",
                                    FI_HOOK_STATE_DIR=str(Path(tmp, "state")))
                command = dict(commands("fi-hook-to-otlp.json"))["PostToolUse"]
                bare = re.fullmatch(r"\((.*)\)", command).group(1)
                run_hook(bare, project, payload_for("PostToolUse", "bare"), env, transport="heredoc")
                self.assertEqual(rx.spans(), [])
                run_hook(command, project, payload_for("PostToolUse", "bare"), env, transport="heredoc")
                self.assertTrue(any(s["name"] == "read_file" for s in rx.spans()))
        finally:
            rx.close()


class KiroIdeInstallerTest(unittest.TestCase):
    def install(self, project, home, *args, cwd=None):
        return subprocess.run([str(EXAMPLE / "install.sh"), *(args or (str(project),))], capture_output=True,
                              text=True, env={"PATH": os.environ.get("PATH", ""), "HOME": str(home)},
                              cwd=cwd or project.parent)

    def test_refuses_when_the_kiro_cli_recipe_shares_a_scope(self):
        for where in ("project", "home"):
            with tempfile.TemporaryDirectory() as tmp:
                project, home = Path(tmp, "project"), Path(tmp, "home")
                base = (project if where == "project" else home) / ".kiro" / "hooks"
                base.mkdir(parents=True)
                project.mkdir(exist_ok=True)
                home.mkdir(exist_ok=True)
                (base / "fi-hook-to-otlp-kiro-cli.json").write_text('{"command": "emit.py kiro_cli"}')
                result = self.install(project, home)
                self.assertEqual(result.returncode, 1, where)
                self.assertIn("Kiro CLI recipe", result.stderr)
                self.assertFalse((project / ".kiro" / "hooks" / "fi-hook-to-otlp.json").exists(), where)

    def test_keeps_an_existing_hook_file_and_says_when_it_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, home = Path(tmp, "project"), Path(tmp, "home")
            hooks = project / ".kiro" / "hooks"
            hooks.mkdir(parents=True)
            home.mkdir()
            old = '{"hooks": [{"action": {"command": "python3 .kiro/fi-hook-to-otlp/emit.py kiro_ide"}}]}'
            (hooks / "fi-hook-to-otlp.json").write_text(old)
            result = self.install(project, home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("differs from the shipped template", result.stdout)
            self.assertEqual((hooks / "fi-hook-to-otlp.json").read_text(), old)

    def test_warns_when_a_kiro_cli_agent_profile_runs_the_cli_recipe(self):
        # The Kiro CLI recipe's --agent-profile entries, as pasted into a CLI agent profile.
        cli_entries = json.dumps({"hooks": [{"trigger": "Stop", "action": {
            "type": "command",
            "command": '(python3 -B "$HOME/.kiro/fi-hook-to-otlp-kiro-cli/emit.py" kiro_cli Stop 2>/dev/null || true)'}}]})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()  # matches the installer's working-directory paths (/var -> /private/var)
            project, home = root / "project", root / "home"
            project.mkdir()
            home.mkdir()
            self.assertEqual(self.install(project, home).stderr, "")
            (project / ".kiro/hooks/fi-hook-to-otlp.json").unlink()

            profile = home / ".kiro/agents/team/reviewer.json"
            profile.parent.mkdir(parents=True)
            profile.write_text(cli_entries)
            result = self.install(project, home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"warning: {profile} is a Kiro CLI agent profile", result.stderr)
            self.assertIn(f"sessions that use that agent in {project} also load this hook file", result.stderr)
            self.assertTrue((project / ".kiro/hooks/fi-hook-to-otlp.json").exists(), "a warning, not a refusal")

            local = project / ".kiro/agents/local.md"
            local.parent.mkdir(parents=True)
            local.write_text(f"---\nname: local\n---\n{cli_entries}")
            result = self.install(project, home, "--user", cwd=project)
            self.assertEqual(result.returncode, 0, result.stderr)
            for path in (profile, local):
                self.assertIn(f"warning: {path} is a Kiro CLI agent profile", result.stderr)
            # From the home directory, ~/.kiro/agents is listed once, not again as a project's agents.
            result = self.install(project, home, "--user", cwd=home)
            self.assertEqual(result.stderr.count("warning:"), 1, result.stderr)


if __name__ == "__main__":
    unittest.main()
