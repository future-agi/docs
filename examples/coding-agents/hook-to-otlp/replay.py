#!/usr/bin/env python3
"""Replay recorded hook payloads through emit.py, one subprocess per hook.

Each line of the JSONL file is ``{"event": "<hook name>", "payload": {...}}``.
The emitter runs exactly as a host app would run it (stdin payload, stdout
response), with the current environment.

    python3 replay.py cursor tests/fixtures/cursor/session.jsonl \
        --replace fixture-conv-0001=my-run-123 --sleep 0.2

``--replace OLD=NEW`` rewrites every occurrence of OLD inside string values
(use it to give each run a fresh session id; it also rewrites ids that carry
a suffix, such as Cursor's ``<generation_id>-0-ab12``). Prints one line per
hook: the event and the stdout the host would receive.

``--hooks-json PATH`` runs the commands registered in an installed hooks file
instead (every ``"command"`` under ``hooks.<event>``), through ``$SHELL -c``
in ``--cwd``, with the payload on stdin or, with ``--transport heredoc``,
appended as ``<command> <<'CURSOR_HOOK_EOF'`` the way Cursor's headless agent
host passes it. Events with no registered command are skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

EMIT = Path(__file__).resolve().parent / "emit.py"


def rewrite(value: Any, mapping: Dict[str, str]) -> Any:
    if isinstance(value, str):
        for old, new in mapping.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [rewrite(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: rewrite(v, mapping) for k, v in value.items()}
    return value


def registered_commands(node: Any) -> List[str]:
    """Every "command" string under a hooks-file entry (flat or nested matcher lists)."""
    if isinstance(node, dict):
        found = [node["command"]] if isinstance(node.get("command"), str) else []
        return found + [c for k, v in node.items() if k != "command" for c in registered_commands(v)]
    if isinstance(node, list):
        return [c for item in node for c in registered_commands(item)]
    return []


def run_command(command: str, text: str, args: argparse.Namespace) -> subprocess.CompletedProcess:
    if args.transport == "heredoc":
        script = f"{command} <<'CURSOR_HOOK_EOF'\n{text}\nCURSOR_HOOK_EOF"
        return subprocess.run([args.shell, "-c", script], cwd=args.cwd, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=30)
    return subprocess.run([args.shell, "-c", command], cwd=args.cwd, input=text,
                          capture_output=True, text=True, timeout=30)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app")
    ap.add_argument("jsonl")
    ap.add_argument("--replace", action="append", default=[], metavar="OLD=NEW")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between hooks")
    ap.add_argument("--pass-event", action="store_true", help="also pass the event name as argv")
    ap.add_argument("--hooks-json", help="run the commands registered in this hooks file")
    ap.add_argument("--cwd", help="working directory for --hooks-json commands")
    ap.add_argument("--transport", choices=("stdin", "heredoc"), default="stdin",
                    help="how --hooks-json commands get the payload")
    ap.add_argument("--shell", default=os.environ.get("SHELL") or "/bin/sh",
                    help="shell for --hooks-json commands (default $SHELL)")
    args = ap.parse_args()
    mapping = dict(item.split("=", 1) for item in args.replace)
    hooks = json.loads(Path(args.hooks_json).read_text(encoding="utf-8"))["hooks"] if args.hooks_json else None
    for line in Path(args.jsonl).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        event = record["event"]
        payload = rewrite(record["payload"], mapping)
        text = json.dumps(payload)
        started = time.monotonic()
        if hooks is not None:
            cmds = registered_commands(hooks.get(event))
            if not cmds:
                print(f"{event:22s} not registered, skipped")
                continue
            results = [run_command(cmd, text, args) for cmd in cmds]
        else:
            argv = [sys.executable, "-B", str(EMIT), args.app] + ([event] if args.pass_event else [])
            results = [subprocess.run(argv, input=text, capture_output=True, text=True, timeout=30)]
        took = (time.monotonic() - started) * 1000
        for result in results:
            print(f"{event:22s} exit={result.returncode} {took:6.0f}ms stdout={result.stdout.strip()}")
        if args.sleep:
            time.sleep(args.sleep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
