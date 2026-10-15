"""Google Antigravity IDE hooks -> normalized span events.

Payload shapes: https://antigravity.google/docs/hooks?tab=ide (read
2026-10-14), checked against the hook protobuf schema shipped in Antigravity
IDE 2.5.5 (``exa.hooks_pb`` in the language server). Payloads are camelCase and
do NOT name the event, so the hook command passes it on argv
(``emit.py antigravity PreToolUse``). Every payload carries ``conversationId``
(the session) and ``modelName``.

    SessionStart    -> session start
    PreInvocation   -> model call start (key = initialNumSteps + invocationNum);
                       invocationNum 0 also opens a turn (one user message)
    PostInvocation  -> model call end
    PostToolUse     -> completed tool span            toolCall.args/result = content,
                       (gen_ai.tool.call.id = step-<stepIdx>), ERROR when ``error`` is set
    Stop            -> turn end                        ERROR when terminationReason is "error"

PreToolUse is a permission hook (its ``decision`` can auto-allow, deny or ask), so
the recipe does not register it and the adapter ignores it: tool spans come from
PostToolUse alone, without a duration. The payloads are protojson, which may
leave out zero values, so a missing ``invocationNum`` is read as 0.

Antigravity has no session-end hook, so the session span is re-exported with
every batch and stays open in between.

The Antigravity app, CLI and IDE share this hook schema but keep conversations
in different app data directories (``~/.gemini/antigravity``,
``~/.gemini/antigravity-cli``, ``~/.gemini/antigravity-ide``). This adapter is
for the IDE: an event whose ``artifactDirectoryPath`` / ``transcriptPath``
sits under the app or CLI directory is dropped (POSIX or Windows separators).
The path is only compared as a string; it is never opened or exported.

Never exported and never opened: ``transcriptPath``, ``artifactDirectoryPath``,
``workspacePaths``. ``lastUserInput``, ``result``, ``modelOutput`` and
``finalModelOutput`` (fields of the 2.5.5 schema, not on the docs page) are
treated as content.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from adapters.base import (
    END, ERROR, LLM, OK, SESSION, START, TOOL, TURN, SpanEvent, compact, first, number,
)

APP = "antigravity"
DISPLAY_NAME = "Antigravity"
SERVICE_NAME = "antigravity-ide"

OTHER_SURFACES = ("/.gemini/antigravity/", "/.gemini/antigravity-cli/")
EVENTS = ("SessionStart", "PreInvocation", "PostInvocation", "PostToolUse", "Stop")
_ENUM = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def event_name(argv_event: Optional[str], payload: Dict[str, Any]) -> Optional[str]:
    return argv_event  # Antigravity payloads do not carry the event name


def respond(event: str, payload: Dict[str, Any]) -> str:
    # Stop accepts a non-continue decision. The emitter never approves tools.
    if event == "Stop":
        return '{"decision": ""}'
    return "{}"


def _int(value: Any) -> Optional[int]:
    n = number(value)
    return int(n) if n is not None else None


def _num(payload: Dict[str, Any], key: str) -> int:
    """protojson omits zero-valued scalars: a missing counter is 0."""
    value = _int(payload.get(key))
    return value if value is not None else 0


def _llm_key(payload: Dict[str, Any]) -> str:
    return f"inv-{_num(payload, 'initialNumSteps')}-{_num(payload, 'invocationNum')}"


def _tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    call = payload.get("toolCall")
    return call if isinstance(call, dict) else {}


def _other_surface(payload: Dict[str, Any]) -> bool:
    for key in ("artifactDirectoryPath", "transcriptPath"):
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.replace("\\", "/")
            if any(marker in normalized for marker in OTHER_SURFACES):
                return True
    return False


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    conversation = first(payload, "conversationId")
    if not conversation or event not in EVENTS or _other_surface(payload):
        return []  # never invent a session id; IDE sessions only
    sid = str(conversation)
    model = first(payload, "modelName")
    model = str(model) if model is not None else None

    if event == "SessionStart":
        return [SpanEvent(START, SESSION, sid, model=model)]

    if event == "PreInvocation":
        invocation = _num(payload, "invocationNum")
        events = []
        if invocation == 0:
            events.append(SpanEvent(START, TURN, sid, model=model, input=payload.get("lastUserInput")))
        events.append(SpanEvent(START, LLM, sid, key=_llm_key(payload), name="Model call", model=model,
                                attributes=compact({
                                    "antigravity.invocation.num": invocation,
                                    "antigravity.initial_num_steps": _num(payload, "initialNumSteps"),
                                })))
        return events

    if event == "PostInvocation":
        return [SpanEvent(END, LLM, sid, key=_llm_key(payload), name="Model call", model=model, status=OK,
                          output=payload.get("modelOutput"),
                          attributes=compact({"antigravity.invocation.num": _num(payload, "invocationNum")}))]

    if event == "PostToolUse":
        call = _tool(payload)
        tool = str(call.get("name") or "tool")
        step = _int(payload.get("stepIdx"))
        key = f"step-{step}" if step is not None else ""
        attrs = compact({"antigravity.tool.name": tool, "antigravity.step.index": step})
        error = payload.get("error")
        failed = bool(error)
        return [SpanEvent(END, TOOL, sid, key=key, name=tool,
                          status=ERROR if failed else OK,
                          status_message="tool error" if failed else None,
                          input=call.get("args"), output=payload.get("result"),
                          error_message=error if failed else None, attributes=attrs)]

    # Stop
    reason = payload.get("terminationReason")
    failed = reason == "error" or bool(payload.get("error"))
    return [SpanEvent(END, TURN, sid, model=model,
                      status=ERROR if failed else OK,
                      status_message="execution ended with error" if failed else None,
                      output=payload.get("finalModelOutput"),
                      error_message=payload.get("error") or None,
                      attributes=compact({
                          "antigravity.stop.termination_reason": reason if isinstance(reason, str) and _ENUM.match(reason) else None,
                          "antigravity.stop.execution_num": _int(payload.get("executionNum")),
                          "antigravity.stop.fully_idle": payload.get("fullyIdle") if isinstance(payload.get("fullyIdle"), bool) else None,
                      }))]
