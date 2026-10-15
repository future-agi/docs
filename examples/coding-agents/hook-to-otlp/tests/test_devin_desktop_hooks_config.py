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
import textwrap
import unittest
from pathlib import Path

from tests.helpers import ROOT, Receiver, all_spans

APP_DIR = ROOT.parent / "devin-desktop"
HOOKS = json.loads((APP_DIR / "hooks.json").read_text(encoding="utf-8"))["hooks"]
PAGE = (ROOT.parents[2] / "src/pages/docs/integrations/coding-agents/devin-desktop.mdx").read_text(encoding="utf-8")
BASH = shutil.which("bash") or "/bin/bash"


def page_bash_block(after: str) -> str:
    """The first ```bash block on the page after the heading or text ``after``, dedented."""
    section = PAGE.split(after, 1)[1]
    block = section.split("```bash\n", 1)[1].split("```", 1)[0]
    return textwrap.dedent(block)
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
        block = PAGE.split("```json\n", 1)[1].split("\n```", 1)[0]
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

    def install(self) -> subprocess.CompletedProcess:
        result = subprocess.run([BASH, str(APP_DIR / "install.sh")], capture_output=True, text=True,
                                env={"PATH": os.environ.get("PATH", ""), "HOME": self.home}, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def write_env_file(self, receiver: Receiver) -> Path:
        """The page's env file, pointed at a local receiver instead of Future AGI."""
        env_file = Path(self.home, ".config/fi-hook-to-otlp/env")
        env_file.parent.mkdir(parents=True)
        env_file.write_text(f"FI_API_KEY=k\nFI_SECRET_KEY=s\nFI_HOOK_SYNC=1\n"
                            f"FI_OTLP_ENDPOINT={receiver.url}/v1/traces\n"
                            f"FI_HOOK_LOG_FILE={self.home}/fi-hook.log\n", encoding="utf-8")
        return env_file

    def tmpdir(self) -> str:
        """A TMPDIR with a trailing slash, as macOS sets it."""
        path = os.path.join(self.home, "tmp")
        os.mkdir(path)
        return path + "/"

    def log_lines(self) -> list:
        log = Path(self.home, "fi-hook.log")
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def test_page_manual_hook_run_sends_one_test_trace_unless_disabled(self):
        self.install()
        receiver = Receiver()
        try:
            self.write_env_file(receiver)
            tmp = self.tmpdir()
            command = page_bash_block("Run one hook by hand")
            self.assertIn("put `FI_HOOK_DISABLED=1` in front of `python3`", PAGE)
            disabled = command.replace("| python3 ", "| FI_HOOK_DISABLED=1 python3 ", 1)
            self.assertNotEqual(disabled, command)
            result = run(disabled, BASH, "stdin", self.home, "", TMPDIR=tmp)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
            self.assertEqual((receiver.requests, self.log_lines()), ([], []), "disabled: nothing sent or logged")
            self.assertEqual(list(Path(tmp).rglob("*.json")), [], "disabled: no state written")

            result = run(command, BASH, "stdin", self.home, "", TMPDIR=tmp)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
            receiver.wait_for(1)
            self.assertEqual(len(receiver.requests), 1)
            spans = all_spans(receiver.requests[0][2])
            self.assertEqual(sorted(s["name"] for s in spans), ["Cascade session", "read_code"])
            self.assertIn("one test trace to your project (a **Cascade session** with session id `fi-hook-test`"
                          " and one **read_code** span)", PAGE)
            for span in spans:
                sid = [a["value"]["stringValue"] for a in span["attributes"] if a["key"] == "session.id"]
                self.assertEqual(sid, ["fi-hook-test"], span["name"])
            lines = self.log_lines()
            self.assertEqual(len(lines), 1)
            self.assertIn("http=200", lines[0])
        finally:
            receiver.close()

    def test_no_keys_means_no_log_lines(self):
        # Troubleshooting step 1: without keys (or with FI_HOOK_DISABLED=1) the emitter logs nothing.
        self.install()
        receiver = Receiver()
        try:
            env_file = self.write_env_file(receiver)
            keyed = env_file.read_text(encoding="utf-8")
            command = HOOKS["post_read_code"][0]["command"]
            for label, text in (("no keys", keyed.replace("FI_API_KEY=k\nFI_SECRET_KEY=s\n", "")),
                                ("disabled", keyed + "FI_HOOK_DISABLED=1\n")):
                env_file.write_text(text, encoding="utf-8")
                result = run(command, BASH, "stdin", self.home, payload("post_read_code"),
                             FI_HOOK_STATE_DIR=os.path.join(self.home, "state"))
                self.assertEqual((result.returncode, result.stdout), (0, ""), label)
                self.assertEqual((receiver.requests, self.log_lines()), ([], []), label)
        finally:
            receiver.close()

    def test_page_uninstall_removes_emitter_state_and_keys(self):
        install = self.install()
        self.assertIn("~/.config/fi-hook-to-otlp/env", install.stdout)
        self.assertIn(f"fi-hook-to-otlp-{os.getuid()}/devin_desktop", install.stdout)
        receiver = Receiver()
        try:
            env_file = self.write_env_file(receiver)
            tmp = self.tmpdir()
            for event in ("pre_user_prompt", "post_read_code"):  # default state dir under TMPDIR
                result = run(HOOKS[event][0]["command"], BASH, "stdin", self.home, payload(event), TMPDIR=tmp)
                self.assertEqual(result.returncode, 0, event)
        finally:
            receiver.close()
        state_dir = Path(tmp, f"fi-hook-to-otlp-{os.getuid()}", "devin_desktop")
        self.assertTrue(list(state_dir.glob("*.json")), "a hook left a state file")
        emitter_dir = Path(self.home, ".codeium/windsurf/fi-hook-to-otlp")
        self.assertTrue(emitter_dir.is_dir())

        result = run(page_bash_block("## Uninstall"), BASH, "stdin", self.home, "", TMPDIR=tmp)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertFalse(emitter_dir.exists())
        self.assertFalse(state_dir.exists())
        self.assertFalse(env_file.exists())
        self.assertTrue(Path(self.home, ".codeium/windsurf/hooks.json").exists(), "hooks.json is edited by hand")
        # A second run (nothing left to delete) still succeeds.
        result = run(page_bash_block("## Uninstall"), BASH, "stdin", self.home, "", TMPDIR=tmp)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installed_commands_read_the_payload_and_print_nothing(self):
        self.install()
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
