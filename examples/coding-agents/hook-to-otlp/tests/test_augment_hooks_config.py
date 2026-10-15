"""The shipped Auggie hooks must never block or steer Auggie, with or without the emitter.

How Auggie 0.36.0 runs a hook command on macOS/Linux (read from the @augmentcode/auggie bundle,
functions dao/QIt/cao/E7n and vao; Augment documents the command as "path to the script"):

- A command with no shell metacharacter is executed directly (spawn, shell: false). If it contains
  a space it is first split into words, honouring single and double quotes.
- A command that starts with ``~`` or contains one of ``| & ; > < $ ` `` runs as ``bash -c <command>``.
- The event JSON is written to the process's stdin. Exit code 2 blocks only on PreToolUse; any
  other non-zero exit, or a command that cannot be started, is logged and the session continues.
  Exit 0 stdout is read as JSON (SessionStart output is added to the agent's context, a Stop
  ``{"decision": "block"}`` keeps the agent working), so the hook must print nothing.

The documented command is a ``.sh`` path executed without a shell, so a ``|| true`` guard in
settings.json would not be honoured. The guard is in futureagi-hook.sh, which runs
``(python3 -B emit.py augment 2>/dev/null || true) >/dev/null`` and exits 0. These tests run
every shipped command the way Auggie does, and also through ``sh -c`` with the payload on stdin
and as a trailing heredoc, with the emitter installed, with emit.py missing and with python3
missing. If the whole install folder is deleted, Auggie cannot start the wrapper; 0.36.0 logs
that as a failed hook and continues (none of the registered events can block).
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

EXAMPLE = Path(__file__).resolve().parents[2] / "augment-code"
TEMPLATE_COMMAND = "/Users/you/.augment/fi-hook-to-otlp/futureagi-hook.sh"
OBSERVE_EVENTS = ["SessionStart", "PostToolUse", "Stop", "SessionEnd"]
SHELLS = [sh for sh in ("/bin/sh", "/bin/bash", "/bin/zsh", "/bin/dash") if os.path.exists(sh)]
# Home directories that break naive quoting: a space, JSON and sed specials, shell specials.
HOMES = ["home", "my home", "odd &#\"\\$HOME`x`"]

_META = re.compile(r"[|&;><$`]")
_WORDS = re.compile(r'"([^"]*(?:\\.[^"]*)*)"|\'([^\']*(?:\\.[^\']*)*)\'|(\S+)')


def auggie_argv(command, args=()):
    """Port of Auggie 0.36.0's POSIX command resolution (dao, QIt, E7n, cao)."""
    if command.startswith("~") or (not args and _META.search(command)):
        return ["bash", "-c", f"{command} {' '.join(args)}" if args else command]
    if not args and " " in command:
        words = [next(g for g in m.groups() if g is not None) for m in _WORDS.finditer(command)]
        return words or [command]
    return [command, *args]


def commands(settings):
    return [(event, hook) for event, groups in settings["hooks"].items()
            for group in groups for hook in group["hooks"]]


def payload(event, sid, cwd):
    body = {"hook_event_name": event, "conversation_id": sid, "workspace_roots": [str(cwd)]}
    if event == "PostToolUse":
        body.update(tool_name="view", tool_input={"path": "README.md"},
                    tool_output="it's $HOME `id` \"quoted\" OUTPUT_MARK", is_mcp_tool=False)
    if event == "Stop":
        body["agent_stop_cause"] = "end_turn"
    return body


def run_hook(command, body, env, cwd, transport, shell="/bin/sh"):
    text = json.dumps(body, indent=2)  # Auggie serializes the event with indent 2
    if transport == "auggie":
        argv = auggie_argv(command)
        return subprocess.run(argv, cwd=cwd, input=text, capture_output=True, text=True, env=env,
                              timeout=30)
    if transport == "stdin":
        return subprocess.run([shell, "-c", command], cwd=cwd, input=text, capture_output=True,
                              text=True, env=env, timeout=30)
    script = f"{command} <<'AUGGIE_HOOK_EOF'\n{text}\nAUGGIE_HOOK_EOF"
    return subprocess.run([shell, "-c", script], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, env=env, timeout=30)


def shells_without_python(tmp):
    """A PATH with sh and bash but no python3."""
    bin_dir = Path(tmp, "no-python-bin")
    bin_dir.mkdir()
    for name in ("sh", "bash"):
        os.symlink(f"/bin/{name}", bin_dir / name)
    return str(bin_dir)


class AugmentHooksConfigTest(unittest.TestCase):
    def base_env(self, home, **extra):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home)}
        env.update(extra)
        return env

    def install(self, tmp, home_name, *args):
        home = Path(tmp, home_name)
        home.mkdir()
        result = subprocess.run([str(EXAMPLE / "install.sh"), *args], capture_output=True, text=True,
                                env=self.base_env(home))
        self.assertEqual(result.returncode, 0, result.stderr)
        return home

    def test_template_registers_observation_hooks_only(self):
        settings = json.loads((EXAMPLE / "settings.json").read_text())
        self.assertEqual(list(settings["hooks"]), OBSERVE_EVENTS)  # never PreToolUse
        for event, hook in commands(settings):
            self.assertEqual(hook, {"type": "command", "command": TEMPLATE_COMMAND, "timeout": 5000}, event)
        self.assertNotIn("metadata", json.dumps(settings))  # no includeUserContext / ConversationData

    def test_installed_commands_send_the_payload_and_print_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp, "project")
            project.mkdir()
            for home_name in HOMES:
                home = self.install(tmp, home_name)
                wrapper = home / ".augment" / "fi-hook-to-otlp" / "futureagi-hook.sh"
                settings = json.loads((home / ".augment" / "settings.json").read_text())
                runs = [("auggie", "/bin/sh"), ("stdin", "/bin/sh"), ("heredoc", "/bin/sh")]
                if home_name == "home":
                    runs += [(t, sh) for sh in SHELLS for t in ("stdin", "heredoc")]
                for transport, shell in runs:
                    label = f"{home_name!r} {transport} {shell}"
                    for _event, hook in commands(settings):
                        argv = auggie_argv(hook["command"])
                        self.assertIn(str(wrapper), argv[-1] if argv[0] == "bash" else argv[0], label)
                    rx = Receiver()
                    try:
                        sid = f"cfg-{len(home_name)}-{transport}-{Path(shell).name}"
                        env = self.base_env(home, FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                                            FI_HOOK_CAPTURE_CONTENT="1",
                                            FI_OTLP_ENDPOINT=rx.url + "/tracer/v1/traces",
                                            FI_HOOK_STATE_DIR=str(Path(tmp, f"state-{sid}")))
                        for event, hook in commands(settings):
                            result = run_hook(hook["command"], payload(event, sid, project), env, project,
                                              transport, shell)
                            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""),
                                             f"{label} {event}")
                        spans = rx.spans()
                    finally:
                        rx.close()
                    names = {s["name"] for s in spans}
                    self.assertTrue({"view", "Agent stop", "Auggie session"} <= names, f"{label}: {names}")
                    view = [s for s in spans if s["name"] == "view"][-1]
                    self.assertEqual(attrs(view)["session.id"], sid, label)
                    # The heredoc is quoted: no expansion of $HOME, backticks or quotes on the way in.
                    self.assertEqual(attrs(view)["output.value"], payload("PostToolUse", sid, project)["tool_output"],
                                     label)
                self.assertEqual(list(home.rglob("__pycache__")), [], "-B keeps bytecode out")

    def test_missing_emitter_or_python_exits_0_with_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.install(tmp, "home")
            (home / ".augment" / "fi-hook-to-otlp" / "emit.py").unlink()
            settings = json.loads((home / ".augment" / "settings.json").read_text())
            no_python = shells_without_python(tmp)
            for path_label, path in (("emit.py missing", None), ("python3 missing", no_python)):
                env = self.base_env(home, **({"PATH": path} if path else {}))
                for shell in SHELLS:
                    for transport in ("auggie", "stdin", "heredoc"):
                        if transport == "auggie" and shell != SHELLS[0]:
                            continue
                        for event, hook in commands(settings):
                            result = run_hook(hook["command"], payload(event, "cfg-missing", tmp), env, tmp,
                                              transport, shell)
                            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""),
                                             f"{path_label} {shell} {transport} {event}")

    def test_project_install_writes_only_the_workspace_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            home = self.install(tmp, "home", "--project", str(repo))
            local = repo / ".augment" / "settings.local.json"
            self.assertTrue(local.exists())
            self.assertFalse((home / ".augment" / "settings.json").exists())
            wrapper = home / ".augment" / "fi-hook-to-otlp" / "futureagi-hook.sh"
            for _event, hook in commands(json.loads(local.read_text())):
                self.assertEqual(auggie_argv(hook["command"]), [str(wrapper)])

    def test_existing_settings_file_is_never_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp, "home")
            (home / ".augment").mkdir(parents=True)
            existing = home / ".augment" / "settings.json"
            existing.write_text('{"model": "keep-me"}\n')
            result = subprocess.run([str(EXAMPLE / "install.sh")], capture_output=True, text=True,
                                    env=self.base_env(home))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(existing.read_text(), '{"model": "keep-me"}\n')
            self.assertIn("merge these entries", result.stdout)
            self.assertIn(str(home / ".augment" / "fi-hook-to-otlp" / "futureagi-hook.sh"), result.stdout)


if __name__ == "__main__":
    unittest.main()
