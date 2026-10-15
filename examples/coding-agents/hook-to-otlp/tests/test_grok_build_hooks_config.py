"""The shipped Grok Build hook file, run the way grok runs inline commands.

grok runs a hook ``command`` as ``sh -c`` on Unix and passes the event as one
line of JSON on stdin (bundled hooks guide, grok 1.0.52). Checked on the real
grok 1.0.52 binary: with the emitter folder removed, the guarded commands let
the prompt run, while the same command without the guard cancelled it,
because ``UserPromptSubmit`` treats exit 2 as "block".

Every shipped command is the subshell ``(python3 -B ... 2>/dev/null || true)``
used by every hook recipe of the family. Each one is run here through several
POSIX shells with the payload on stdin (grok's transport) and as a trailing
heredoc (the other transport hosts use): emitter missing, python3 missing,
and installed. It must exit 0, print nothing when the emitter is missing,
print ``{}`` (no decision) when installed, and the payload must reach the
emitter.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, Receiver, attrs

APP_DIR = ROOT.parent / "grok-build"
HOOKS = json.loads((APP_DIR / "futureagi.json").read_text(encoding="utf-8"))["hooks"]
EXPECTED = {"SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "PermissionDenied",
            "Stop", "StopFailure", "StopCancelled", "SubagentStart", "SubagentStop", "PostCompact", "SessionEnd"}
TRANSPORTS = ("stdin", "heredoc")
SHELLS = [sh for sh in ("/bin/sh", "/bin/bash", "/bin/zsh", "/bin/dash") if os.path.exists(sh)]
PROMPT = "it's $HOME `id` \"quoted\" PROMPT_MARK"


def command(event: str) -> str:
    (group,) = HOOKS[event]
    (hook,) = group["hooks"]
    return hook["command"]


def payload(event: str, session: str = "cfg-session", **extra) -> str:
    body = {"hookEventName": event, "hook_event_name": event, "sessionId": session,
            "cwd": "/tmp", "workspaceRoot": "/tmp", "promptId": "cfg-prompt"}
    body.update(extra)
    return json.dumps(body)


def run(cmd: str, home: str, text: str, shell: str = "/bin/sh", transport: str = "stdin",
        **env: str) -> subprocess.CompletedProcess:
    full = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home}
    full.update(env)
    if transport == "stdin":
        return subprocess.run([shell, "-c", cmd], input=text, capture_output=True, text=True,
                              env=full, cwd=home, timeout=30)
    script = f"{cmd} <<'GROK_HOOK_EOF'\n{text}\nGROK_HOOK_EOF"
    return subprocess.run([shell, "-c", script], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          env=full, cwd=home, timeout=30)


class GrokBuildHooksConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def install(self) -> None:
        result = subprocess.run(["bash", str(APP_DIR / "install.sh")], capture_output=True, text=True,
                                env={"PATH": os.environ.get("PATH", ""), "HOME": self.home}, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = json.loads(Path(self.home, ".grok/hooks/futureagi.json").read_text())["hooks"]
        self.assertEqual(installed, HOOKS)

    def test_registered_hooks_are_observation_only_guarded_subshells(self):
        self.assertEqual(set(HOOKS), EXPECTED)
        self.assertNotIn("PreToolUse", HOOKS)  # the deny-capable event is never registered
        for event in HOOKS:
            (group,) = HOOKS[event]
            self.assertNotIn("matcher", group, event)
            (hook,) = group["hooks"]
            self.assertEqual((hook["type"], hook["timeout"]), ("command", 5), event)
            self.assertEqual(hook["command"],
                             f'(python3 -B "$HOME/.grok/fi-hook-to-otlp/emit.py" grok_build {event} 2>/dev/null || true)')

    def test_page_shows_the_shipped_hook_file(self):
        page = (ROOT.parents[2] / "src/pages/docs/integrations/coding-agents/grok-build.mdx").read_text(encoding="utf-8")
        block = page.split("```json\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(json.loads(block)["hooks"], HOOKS)

    def test_missing_emitter_exits_0_with_empty_output(self):
        for shell in SHELLS:
            for transport in TRANSPORTS:
                for event in HOOKS:
                    result = run(command(event), self.home, payload(event), shell, transport)
                    self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""),
                                     f"{shell} {transport} {event}")

    def test_missing_python_exits_0_with_empty_output(self):
        with tempfile.TemporaryDirectory() as empty_bin:
            for shell in SHELLS:
                for transport in TRANSPORTS:
                    for event in HOOKS:
                        result = run(command(event), self.home, payload(event), shell, transport, PATH=empty_bin)
                        self.assertEqual((result.returncode, result.stdout), (0, ""), f"{shell} {transport} {event}")

    def test_installed_commands_get_the_payload_on_stdin_and_as_heredoc(self):
        self.install()
        for shell in SHELLS:
            for transport in TRANSPORTS:
                label = f"{Path(shell).name}-{transport}"
                sid = f"cfg-{label}"
                receiver = Receiver()
                try:
                    env = dict(FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1", FI_HOOK_CAPTURE_CONTENT="1",
                               FI_OTLP_ENDPOINT=f"{receiver.url}/tracer/v1/traces",
                               FI_HOOK_STATE_DIR=os.path.join(self.home, f"state-{label}"))
                    steps = [("SessionStart", {"source": "new"}),
                             ("UserPromptSubmit", {"prompt": PROMPT}),
                             ("PostToolUse", {"toolName": "read_file", "toolUseId": "call_cfg", "durationMs": 5}),
                             ("Stop", {"reason": "end_turn"}),
                             ("SessionEnd", {"reason": "shutdown"})]
                    for event, extra in steps:
                        result = run(command(event), self.home, payload(event, sid, **extra), shell, transport, **env)
                        self.assertEqual(result.returncode, 0, f"{label} {event}")
                        self.assertEqual(json.loads(result.stdout), {}, f"{label} {event}: no decision")
                    spans = receiver.spans()
                finally:
                    receiver.close()
                names = {s["name"] for s in spans}
                self.assertEqual(names, {"read_file", "Grok Build turn", "Grok Build session"}, label)
                self.assertEqual({attrs(s)["session.id"] for s in spans}, {sid}, label)
                turn = [s for s in spans if s["name"] == "Grok Build turn"][-1]
                # The heredoc is quoted: no expansion of $HOME, backticks or quotes on the way in.
                self.assertEqual(attrs(turn)["input.value"], PROMPT, label)
        self.assertEqual(list(Path(self.home).rglob("__pycache__")), [], "-B writes no bytecode")

    def test_unparenthesized_guard_would_lose_a_heredoc_payload(self):
        # Why the parentheses are required: `cmd || true <<EOF` feeds the heredoc to `true`.
        self.install()
        receiver = Receiver()
        try:
            env = dict(FI_API_KEY="k", FI_SECRET_KEY="s", FI_HOOK_SYNC="1",
                       FI_OTLP_ENDPOINT=f"{receiver.url}/tracer/v1/traces",
                       FI_HOOK_STATE_DIR=os.path.join(self.home, "state"))
            tool = payload("PostToolUse", toolName="read_file", toolUseId="call_bare", durationMs=5)
            bare = re.fullmatch(r"\((.*)\)", command("PostToolUse")).group(1)
            run(bare, self.home, tool, transport="heredoc", **env)
            self.assertEqual(receiver.spans(), [])
            run(command("PostToolUse"), self.home, tool, transport="heredoc", **env)
            self.assertTrue(any(s["name"] == "read_file" for s in receiver.spans()))
        finally:
            receiver.close()


if __name__ == "__main__":
    unittest.main()
