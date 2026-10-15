"""Kiro IDE agent hooks -> normalized span events.

Payload shapes: https://kiro.dev/docs/hooks/types/ and /docs/hooks/actions/
(read 2026-10-14), checked against the payload builder shipped in Kiro IDE
1.2.37 (``kiro.kiro-agent`` extension). Every command hook gets JSON on stdin
with ``session_id``, ``hook_event_name`` and ``cwd``; per trigger:

    SessionStart        -> session start
    UserPromptSubmit    -> turn start            prompt = content
    PostToolUse         -> tool span              tool_response = content,
                                                  ERROR when tool_response.success is false
    PostTaskExec        -> spec task span         ERROR when task_success is false

Permission and pre-task hooks are intentionally not registered: this recipe is observe-only.
    PostFileCreate/Save/Delete -> "File ..." event   file path = content
    Stop                -> turn end
    SessionEnd          -> session end           reason kept when it is an enum value

Kiro sends no turn id and no tool call id, so turns and tools pair with the
open turn / the oldest open tool of the same name (empty ``key``).

Ignored: ``AgentSpawn`` / ``agentSpawn`` (Kiro CLI names, not an IDE event),
``Manual``. Never exported: ``cwd``, the ``USER_PROMPT`` environment variable
(the emitter does not read it), file paths outside opted-in content.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from adapters.base import (
    END, ERROR, EVENT, INSTANT, OK, SESSION, START, TOOL, TURN, UPDATE, SpanEvent, compact, first,
)

APP = "kiro_ide"
DISPLAY_NAME = "Kiro IDE"
SERVICE_NAME = "kiro-ide"

FILE_EVENTS = {"PostFileCreate": "File created", "PostFileSave": "File saved", "PostFileDelete": "File deleted"}
_ENUM = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def respond(event: str, payload: Dict[str, Any]) -> str:
    # Kiro adds a successful hook's stdout to the agent context on
    # SessionStart, UserPromptSubmit and PostTaskExec: answer with nothing.
    return ""


def _enum(value: Any) -> Any:
    """Keep short identifier-like values (reasons, decisions); drop free text."""
    return value if isinstance(value, str) and _ENUM.match(value) else None


def _tool_failed(response: Any) -> bool:
    return isinstance(response, dict) and response.get("success") is False


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    session = first(payload, "session_id")
    if not session:
        return []  # never invent a session id
    sid = str(session)

    if event == "SessionStart":
        return [SpanEvent(START, SESSION, sid)]

    if event == "SessionEnd":
        # Kiro fires this when it unloads/reloads a persisted session. Keep the
        # state and turn sequence: SessionEnd is not a terminal chat end.
        return [SpanEvent(UPDATE, SESSION, sid,
                          attributes=compact({"kiro.session.end_reason": _enum(payload.get("reason"))}))]

    if event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        return [SpanEvent(START, TURN, sid, input=prompt, attributes=compact({
            "kiro.prompt.length": len(prompt) if isinstance(prompt, str) else None,
        }))]

    if event == "Stop":
        return [SpanEvent(END, TURN, sid, status=OK)]

    if event == "PostToolUse":
        tool = str(first(payload, "tool_name") or "tool")
        attrs = {"kiro.tool.name": tool}
        response = payload.get("tool_response")
        failed = _tool_failed(response)
        return [SpanEvent(
            END, TOOL, sid, name=tool,
            status=ERROR if failed else OK,
            status_message="tool reported failure" if failed else None,
            input=payload.get("tool_input"),
            output=None if failed else response,
            error_message=response if failed else None,
            attributes=attrs,
        )]

    if event == "PostTaskExec":
        # Observe the completed task only. PreTaskExec is a gating hook.
        names = {"spec": payload.get("spec_name"), "task": payload.get("task_name")}
        success = payload.get("task_success")
        failed = success is False
        return [SpanEvent(INSTANT, EVENT, sid, name="Spec task", input=names,
                          status=ERROR if failed else OK,
                          status_message="spec task failed" if failed else None,
                          attributes=compact({"kiro.event": "spec_task",
                                              "kiro.task.success": success if isinstance(success, bool) else None}))]

    if event in FILE_EVENTS:
        return [SpanEvent(INSTANT, EVENT, sid, name=FILE_EVENTS[event], input=payload.get("file_path"),
                          attributes={"kiro.event": event})]

    return []
