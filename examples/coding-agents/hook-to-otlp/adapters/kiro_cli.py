"""Kiro CLI hooks -> normalized span events.

Payload shapes: https://kiro.dev/docs/hooks/types/, /docs/hooks/actions/ and
/docs/cli/v3/hooks-migration/ (read 2026-10-14), checked against the hook
fields named in the kiro-cli-chat 2.31.1 binary. Every command hook gets JSON
on stdin with ``session_id``, ``hook_event_name`` and ``cwd``.

CLI V3 uses PascalCase triggers; ``SessionStart`` is canonical and
``AgentSpawn`` / ``agentSpawn`` are accepted spellings of it. CLI 2.x
camelCase event names are mapped too.

    SessionStart | AgentSpawn | agentSpawn -> session start
    UserPromptSubmit | userPromptSubmit    -> turn start        prompt = content
    PreToolUse | preToolUse                -> tool start        tool_input = content
    PostToolUse | postToolUse              -> tool end          tool_response = content,
                                              ERROR when tool_response.success is false
    Stop | stop                            -> turn end          assistant_response = content
    SessionEnd                             -> session end (CLI V3)

Kiro sends no turn id and no tool call id, so turns and tools pair with the
open turn / the oldest open tool of the same name (empty ``key``).

Not mapped: file and spec-task triggers (no session/turn/tool meaning), and
``Manual``. Never exported: ``cwd`` and anything under ``KIRO_HOME``; the
emitter reads only the stdin payload.
"""
from __future__ import annotations

from typing import Any, Dict, List

from adapters.base import END, ERROR, OK, SESSION, START, TOOL, TURN, SpanEvent, compact, first

APP = "kiro_cli"
DISPLAY_NAME = "Kiro CLI"
SERVICE_NAME = "kiro-cli"

ALIASES = {
    "SessionStart": "SessionStart", "AgentSpawn": "SessionStart", "agentSpawn": "SessionStart",
    "UserPromptSubmit": "UserPromptSubmit", "userPromptSubmit": "UserPromptSubmit",
    "PreToolUse": "PreToolUse", "preToolUse": "PreToolUse",
    "PostToolUse": "PostToolUse", "postToolUse": "PostToolUse",
    "Stop": "Stop", "stop": "Stop",
    "SessionEnd": "SessionEnd",
}


def respond(event: str, payload: Dict[str, Any]) -> str:
    # Kiro adds a successful hook's stdout to the agent context on SessionStart
    # and UserPromptSubmit, so answer with nothing rather than "{}".
    return ""


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    session = first(payload, "session_id")
    canonical = ALIASES.get(event)
    if not session or canonical is None:
        return []  # never invent a session id
    sid = str(session)
    attrs = {"kiro.hook.trigger": event} if event != canonical else {}

    if canonical == "SessionStart":
        return [SpanEvent(START, SESSION, sid, attributes=attrs)]

    if canonical == "SessionEnd":
        return [SpanEvent(END, SESSION, sid, status=OK)]

    if canonical == "UserPromptSubmit":
        prompt = payload.get("prompt")
        return [SpanEvent(START, TURN, sid, input=prompt, attributes=compact({
            **attrs, "kiro.prompt.length": len(prompt) if isinstance(prompt, str) else None,
        }))]

    if canonical == "Stop":
        return [SpanEvent(END, TURN, sid, status=OK, output=payload.get("assistant_response"), attributes=attrs)]

    tool = str(first(payload, "tool_name") or "tool")
    tool_attrs = {**attrs, "kiro.tool.name": tool}
    if canonical == "PreToolUse":
        return [SpanEvent(START, TOOL, sid, name=tool, input=payload.get("tool_input"), attributes=tool_attrs)]
    response = payload.get("tool_response")
    failed = isinstance(response, dict) and response.get("success") is False
    return [SpanEvent(
        END, TOOL, sid, name=tool,
        status=ERROR if failed else OK,
        status_message="tool reported failure" if failed else None,
        input=payload.get("tool_input"),
        output=None if failed else response,
        error_message=response if failed else None,
        attributes=tool_attrs,
    )]
