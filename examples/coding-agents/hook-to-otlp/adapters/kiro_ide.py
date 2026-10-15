"""Kiro IDE agent hooks -> normalized span events.

Payload shapes: https://kiro.dev/docs/hooks/types/ and /docs/hooks/actions/
(read 2026-10-14), checked against the payload builder shipped in Kiro IDE
1.2.37 (``kiro.kiro-agent`` extension). Every command hook gets JSON on stdin
with ``session_id``, ``hook_event_name`` and ``cwd``; per trigger:

    SessionStart        -> session start
    UserPromptSubmit    -> turn start            prompt = content
    PreToolUse          -> tool start            tool_input = content
    PostToolUse         -> tool end              tool_response = content,
                                                 ERROR when tool_response.success is false
    PreTaskExec         -> spec task start       spec/task names = content
    PostTaskExec        -> spec task end         ERROR when task_success is false
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

import hashlib
import re
from typing import Any, Dict, List

from adapters.base import (
    END, ERROR, EVENT, INSTANT, OK, SESSION, START, TOOL, TURN, SpanEvent, compact, first,
)

APP = "kiro_ide"
DISPLAY_NAME = "Kiro IDE"
SERVICE_NAME = "kiro-ide"

FILE_EVENTS = {"PostFileCreate": "File created", "PostFileSave": "File saved", "PostFileDelete": "File deleted"}
_ENUM = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def respond(event: str, payload: Dict[str, Any]) -> str:
    # Kiro adds a successful hook's stdout to the agent context on
    # SessionStart, UserPromptSubmit and PreTaskExec: answer with nothing.
    return ""


def _enum(value: Any) -> Any:
    """Keep short identifier-like values (reasons, decisions); drop free text."""
    return value if isinstance(value, str) and _ENUM.match(value) else None


def _tool_failed(response: Any) -> bool:
    return isinstance(response, dict) and response.get("success") is False


def _task_key(payload: Dict[str, Any]) -> str:
    raw = f"{payload.get('spec_name')}\x1f{payload.get('task_name')}"
    return "task-" + hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    session = first(payload, "session_id")
    if not session:
        return []  # never invent a session id
    sid = str(session)

    if event == "SessionStart":
        return [SpanEvent(START, SESSION, sid)]

    if event == "SessionEnd":
        return [SpanEvent(END, SESSION, sid, status=OK,
                          attributes=compact({"kiro.session.end_reason": _enum(payload.get("reason"))}))]

    if event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        return [SpanEvent(START, TURN, sid, input=prompt, attributes=compact({
            "kiro.prompt.length": len(prompt) if isinstance(prompt, str) else None,
        }))]

    if event == "Stop":
        return [SpanEvent(END, TURN, sid, status=OK, attributes=compact({
            "kiro.stop.user_decision": _enum(payload.get("user_decision")),
        }))]

    if event in ("PreToolUse", "PostToolUse"):
        tool = str(first(payload, "tool_name") or "tool")
        attrs = {"kiro.tool.name": tool}
        if event == "PreToolUse":
            return [SpanEvent(START, TOOL, sid, name=tool, input=payload.get("tool_input"), attributes=attrs)]
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

    if event in ("PreTaskExec", "PostTaskExec"):
        names = {"spec": payload.get("spec_name"), "task": payload.get("task_name")}
        if event == "PreTaskExec":
            return [SpanEvent(START, EVENT, sid, key=_task_key(payload), name="Spec task", input=names,
                              attributes={"kiro.event": "spec_task"})]
        success = payload.get("task_success")
        failed = success is False
        return [SpanEvent(END, EVENT, sid, key=_task_key(payload), name="Spec task", input=names,
                          status=ERROR if failed else OK,
                          status_message="spec task failed" if failed else None,
                          attributes=compact({"kiro.event": "spec_task",
                                              "kiro.task.success": success if isinstance(success, bool) else None}))]

    if event in FILE_EVENTS:
        return [SpanEvent(INSTANT, EVENT, sid, name=FILE_EVENTS[event], input=payload.get("file_path"),
                          attributes={"kiro.event": event})]

    return []
