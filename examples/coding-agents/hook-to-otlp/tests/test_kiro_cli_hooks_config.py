"""The shipped Kiro CLI hook commands must never block Kiro, with or without the emitter.

Kiro CLI runs a command hook through a shell with the JSON payload on stdin. Exit 2
on PreToolUse blocks the tool and sends stderr to the model (Kiro hook docs, exit
codes), and exit-0 stdout on SessionStart / UserPromptSubmit is added to the agent
context. Every shipped command (standalone project file, global file, and the
agent-profile entries) is the canonical subshell guard
``(python3 -B <emit.py> kiro_cli <Trigger> 2>/dev/null || true)``: exit 0 and no
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

EXAMPLE = Path(__file__).resolve().parents[2] / "kiro-cli"
GATING = {"PreToolUse", "preToolUse"}
GLOBAL = '"$HOME/.kiro/fi-hook-to-otlp-kiro-cli/emit.py"'
CONFIGS = {"fi-hook-to-otlp-kiro-cli.json": ".kiro/fi-hook-to-otlp-kiro-cli/emit.py",
           "fi-hook-to-otlp-kiro-cli.user.json": GLOBAL,
           "agent-profile-hooks.json": GLOBAL}
TRANSPORTS = ("stdin", "heredoc")
SHELLS = [sh for sh in ("/bin/sh", "/bin/zsh", "/bin/bash", "/bin/dash") if os.path.exists(sh)]
PROMPT = "it's $HOME `id` \"quoted\" PROMPT_MARK"


def hooks_of(config_name):
    return json.loads((EXAMPLE / config_name).read_text())["hooks"]


def commands(config_name):
    return [(hook["trigger"], hook["action"]["command"]) for hook in hooks_of(config_name)]


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
        payload["prompt"] = PROMPT
    if trigger == "PostToolUse":
        payload.update(tool_name="read_file", tool_input={"path": "README.md"},
                       tool_response={"success": True, "result": ["ok"]})
    if trigger == "Stop":
        payload["assistant_response"] = "done"
    return payload


def base_env(home=None, **extra):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home or tempfile.gettempdir()}
    env.update(extra)
    return env


class KiroCliHooksConfigTest(unittest.TestCase):
    def test_observe_only_and_every_command_is_the_guarded_subshell(self):
        for name, path in CONFIGS.items():
            triggers = [hook["trigger"] for hook in hooks_of(name)]
            self.assertEqual(triggers, ["SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd"], name)
            for hook in hooks_of(name):
                trigger = hook["trigger"]
                self.assertNotIn(trigger, GATING, f"{name}: {trigger}")
                self.assertEqual(hook["action"]["command"],
                                 f"(python3 -B {path} kiro_cli {trigger} 2>/dev/null || true)", name)
        self.assertNotIn("version", json.loads((EXAMPLE / "agent-profile-hooks.json").read_text()))

    def test_page_snippets_match_the_shipped_commands(self):
        page = (EXAMPLE.parents[2] / "src/pages/docs/integrations/coding-agents/kiro-cli.mdx").read_text()
        self.assertIn(dict(commands("fi-hook-to-otlp-kiro-cli.json"))["PostToolUse"], page)
        for _, command in commands("agent-profile-hooks.json"):
            self.assertIn(command.replace('"', '\\"'), page)
        self.assertNotIn("kiro_cli ||", page)

    def test_missing_emitter_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for name in CONFIGS:
                        for trigger, command in commands(name):
                            result = run_hook(command, empty, payload_for(trigger, "cfg"), base_env(empty),
                                              shell, transport)
                            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""),
                                             f"{shell} {transport} {name} {trigger}")

    def test_missing_python_exits_0_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as empty:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for trigger, command in commands("fi-hook-to-otlp-kiro-cli.json"):
                        result = run_hook(command, empty, payload_for(trigger, "cfg"), base_env(PATH=empty),
                                          shell, transport)
                        self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {transport} {trigger}")

    def run_installed(self, install_args, hook_file_of, cwd_of, shells, kiro_home=None):
        """Install, then run every installed command per shell and transport; return spans per run."""
        results = {}
        with tempfile.TemporaryDirectory() as tmp:
            home, project = Path(tmp, "home"), Path(tmp, "project")
            home.mkdir()
            project.mkdir()
            extra = {"KIRO_HOME": kiro_home(home)} if kiro_home else {}
            done = subprocess.run([str(EXAMPLE / "install.sh"), *install_args(project)], check=True,
                                  capture_output=True, text=True, env=base_env(str(home), **extra))
            hook_file = hook_file_of(project, home, done.stdout)
            for shell in shells:
                for transport in TRANSPORTS:
                    rx = Receiver()
                    try:
                        env = base_env(str(home), FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                       FI_HOOK_CAPTURE_CONTENT="1", FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces",
                                       FI_HOOK_STATE_DIR=str(Path(tmp, f"state-{Path(shell).name}-{transport}")))
                        sid = f"cfg-{Path(shell).name}-{transport}"
                        for hook in hook_file["hooks"]:
                            trigger = hook["trigger"]
                            result = run_hook(hook["action"]["command"], cwd_of(project), payload_for(trigger, sid),
                                              env, shell, transport)
                            self.assertEqual((result.returncode, result.stdout), (0, ""),
                                             f"{shell} {transport} {trigger}")
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
            turn = [s for s in spans if s["name"] == "Kiro CLI turn"][-1]
            # The heredoc is quoted: no expansion of $HOME, backticks or quotes on the way in.
            self.assertEqual(attrs(turn)["input.value"], PROMPT, label)
            self.assertEqual(attrs(turn)["coding_agent.hook.event"], "Stop", label)

    def test_installed_project_hooks_receive_the_payload_on_stdin_and_as_heredoc(self):
        results = self.run_installed(
            lambda project: [str(project)],
            lambda project, home, out: json.loads((project / ".kiro/hooks/fi-hook-to-otlp-kiro-cli.json").read_text()),
            lambda project: project, SHELLS)
        self.assertEqual(len(results), len(SHELLS) * len(TRANSPORTS))
        self.assert_payload_arrived(results)

    def test_installed_user_hooks_receive_the_payload_from_any_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            results = self.run_installed(
                lambda project: ["--user"],
                lambda project, home, out: json.loads((home / ".kiro/hooks/fi-hook-to-otlp-kiro-cli.json").read_text()),
                lambda project: workspace, SHELLS[:1])
        self.assert_payload_arrived(results)

    def test_installed_user_hooks_follow_kiro_home(self):
        with tempfile.TemporaryDirectory() as workspace:
            def hook_file(project, home, out):
                self.assertFalse((home / ".kiro").exists())
                doc = json.loads((home / "kiro home/hooks/fi-hook-to-otlp-kiro-cli.json").read_text())
                self.assertIn(f'"{home}/kiro home/fi-hook-to-otlp-kiro-cli/emit.py"', doc["hooks"][0]["action"]["command"])
                return doc
            results = self.run_installed(lambda project: ["--user"], hook_file, lambda project: workspace,
                                         SHELLS[:1], kiro_home=lambda home: str(home / "kiro home"))
        self.assert_payload_arrived(results)

    def test_agent_profile_install_prints_the_hooks_and_writes_no_hook_file(self):
        with tempfile.TemporaryDirectory() as workspace:
            def hook_file(project, home, out):
                self.assertFalse((home / ".kiro/hooks").exists(), "no standalone hook file")
                printed = out[out.index("{"):out.rindex("}") + 1]
                doc = json.loads(printed)
                self.assertEqual(doc, json.loads((EXAMPLE / "agent-profile-hooks.json").read_text()))
                return doc
            results = self.run_installed(lambda project: ["--agent-profile"], hook_file, lambda project: workspace,
                                         SHELLS[:1])
        self.assert_payload_arrived(results)

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
                command = dict(commands("fi-hook-to-otlp-kiro-cli.json"))["PostToolUse"]
                bare = re.fullmatch(r"\((.*)\)", command).group(1)
                run_hook(bare, project, payload_for("PostToolUse", "bare"), env, transport="heredoc")
                self.assertEqual(rx.spans(), [])
                run_hook(command, project, payload_for("PostToolUse", "bare"), env, transport="heredoc")
                self.assertTrue(any(s["name"] == "read_file" for s in rx.spans()))
        finally:
            rx.close()


class KiroCliInstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Resolved, so paths match what the installer prints from its working directory (/var -> /private/var).
        root = Path(self.tmp.name).resolve()
        self.project, self.home = root / "project", root / "home"
        self.project.mkdir()
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args, cwd=None, **extra):
        # Run from a neutral directory unless a test needs a project as the current directory.
        return subprocess.run([str(EXAMPLE / "install.sh"), *(args or (str(self.project),))], capture_output=True,
                              text=True, env=base_env(str(self.home), **extra), cwd=cwd or self.tmp.name)

    def put(self, path, text='{"command": "emit.py kiro_ide"}'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_refuses_when_the_kiro_ide_recipe_shares_a_scope(self):
        # A global install cannot see every project, so only the scopes it would share are checked.
        for base, args in ((self.project, (str(self.project),)), (self.home, (str(self.project),)),
                           (self.home, ("--user",))):
            hooks = base / ".kiro" / "hooks"
            hooks.mkdir(parents=True, exist_ok=True)
            (hooks / "fi-hook-to-otlp.json").write_text('{"command": "emit.py kiro_ide"}')
            result = self.install(*args)
            self.assertEqual(result.returncode, 1, (base, args))
            self.assertIn("Kiro IDE recipe", result.stderr)
            self.assertEqual(list(Path(self.tmp.name).rglob("fi-hook-to-otlp-kiro-cli.json")), [])
            (hooks / "fi-hook-to-otlp.json").unlink()

    def test_agent_profile_refuses_when_global_hooks_already_run_in_every_session(self):
        # A session that uses an agent profile still loads every ~/.kiro/hooks/*.json file.
        ide = self.put(self.home / ".kiro/hooks/fi-hook-to-otlp.json")
        for extra in ({}, {"KIRO_HOME": str(self.home / "kiro-home")}):
            result = self.install("--agent-profile", **extra)
            self.assertEqual(result.returncode, 1, extra)
            self.assertIn(f"{ide} is the Kiro IDE recipe", result.stderr)
            self.assertIn("exported twice", result.stderr)
            self.assertNotIn('"hooks"', result.stdout, "no entries to paste")
            self.assertEqual(list(Path(self.tmp.name).rglob("emit.py")), [], "nothing installed")
        ide.unlink()

        self.assertEqual(self.install("--user").returncode, 0)
        result = self.install("--agent-profile")
        self.assertEqual(result.returncode, 1)
        self.assertIn("already traces every Kiro CLI session", result.stderr)
        self.assertNotIn('"hooks"', result.stdout)

    def test_agent_profile_warns_when_the_current_project_loads_a_tracing_hook_file(self):
        result = self.install("--agent-profile", cwd=self.project)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertIn("do not use it in a project that has", result.stdout)
        for name in ("fi-hook-to-otlp.json", "fi-hook-to-otlp-kiro-cli.json"):
            other = self.put(self.project / ".kiro/hooks" / name, '{"command": "emit.py kiro_ide kiro_cli"}')
            result = self.install("--agent-profile", cwd=self.project)
            self.assertEqual(result.returncode, 0, name)
            self.assertIn(f"warning: {other} runs in every Kiro session", result.stderr)
            self.assertIn("would be exported twice", result.stderr)
            self.assertIn('"hooks"', result.stdout, "the entries are still printed")
            other.unlink()

    def test_user_install_warns_about_a_project_install_it_doubles(self):
        self.assertEqual(self.install().returncode, 0)
        project_file = self.project / ".kiro/hooks/fi-hook-to-otlp-kiro-cli.json"
        result = self.install("--user", cwd=self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"warning: {project_file} is a project install of this recipe", result.stderr)
        self.assertIn("exported twice", result.stderr)
        self.assertTrue(project_file.exists(), "the project file is left for the user to remove")
        # It cannot see other projects, so it always says what to remove there.
        result = self.install("--user")
        self.assertEqual(result.stderr, "")
        self.assertIn("If you installed this recipe per project before", result.stdout)
        # Run from the home directory, ~/.kiro is the global scope, not a project install.
        for _ in range(2):
            self.assertEqual(self.install("--user", cwd=self.home).stderr, "")

    def test_user_install_warns_about_the_kiro_ide_recipe_in_the_current_project(self):
        ide = self.put(self.project / ".kiro/hooks/fi-hook-to-otlp.json")
        result = self.install("--user", cwd=self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"warning: {ide} is the Kiro IDE recipe", result.stderr)

    def test_warns_when_an_agent_profile_already_runs_the_emitter(self):
        hooks = (EXAMPLE / "agent-profile-hooks.json").read_text()
        profile = self.put(self.home / ".kiro/agents/team/reviewer.json", hooks)
        result = self.install("--user")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"warning: {profile} is an agent profile that runs this recipe's hooks", result.stderr)
        (self.home / ".kiro/hooks/fi-hook-to-otlp-kiro-cli.json").unlink()

        local = self.put(self.project / ".kiro/agents/local.md", f"---\nname: local\n---\n{hooks}")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (profile, local):
            self.assertIn(f"warning: {path} is an agent profile", result.stderr)
        self.assertIn(f"Sessions that use that agent in {self.project} would be exported twice",
                      result.stderr)
        profile.unlink()
        local.unlink()
        self.assertEqual(self.install().stderr, "")

    def test_refuses_a_project_install_when_the_global_one_exists(self):
        self.assertEqual(self.install("--user").returncode, 0)
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("exported twice", result.stderr)

    def test_keeps_an_existing_hook_file_and_says_when_it_is_stale(self):
        hooks = self.project / ".kiro" / "hooks"
        hooks.mkdir(parents=True)
        old = '{"hooks": [{"action": {"command": "python3 .kiro/fi-hook-to-otlp-kiro-cli/emit.py kiro_cli || true"}}]}'
        (hooks / "fi-hook-to-otlp-kiro-cli.json").write_text(old)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("differs from the shipped template", result.stdout)
        self.assertEqual((hooks / "fi-hook-to-otlp-kiro-cli.json").read_text(), old)
        (hooks / "fi-hook-to-otlp-kiro-cli.json").unlink()
        self.assertEqual(self.install().returncode, 0)
        result = self.install()
        self.assertNotIn("differs", result.stdout)

    def test_rejects_a_kiro_home_that_would_break_the_command(self):
        result = subprocess.run([str(EXAMPLE / "install.sh"), "--user"], capture_output=True, text=True,
                                env=base_env(str(self.home), KIRO_HOME=str(self.home / 'a"b')))
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
