"""Grok Build (xAI ``grok`` CLI/TUI) hooks -> normalized span events.

Payload shapes follow https://docs.x.ai/build/features/hooks and the hooks
guide bundled with grok 1.0.52 (``~/.grok/docs/user-guide/10-hooks.md``,
read 2026-10-14), and were checked against payloads captured from a real
grok 1.0.52 session. Every event carries ``sessionId``; turn events carry
``promptId``; tool events carry ``toolName`` and ``toolUseId`` (tool events
carry no ``promptId``, so tools attach to the session's open turn).

Mapped events:

    SessionStart        -> session start
    UserPromptSubmit    -> turn start (key promptId)     prompt = content
    PostToolUse         -> tool span (key toolUseId), start = end - durationMs
                           toolInput / toolResult = content; for shell tools
                           the result's exit_code / timed_out are metadata
                           and a non-zero exit or a timeout is ERROR
    PostToolUseFailure  -> tool end, ERROR               error = content
    PermissionDenied    -> tool end, ERROR "permission denied"
    Stop                -> turn end (only with promptId; the session-end
                           ``Stop`` without promptId is ignored)
    StopFailure         -> turn end, ERROR, status message = classified error
    StopCancelled       -> turn end, status unset, cancel reason recorded
    SubagentStart       -> subagent span in the parent session; its
                           ``subagentId`` is the child session id
    SubagentStop        -> turn end inside the child session
    PostCompact         -> event span "Context compaction"
    SessionEnd          -> session end

A subagent runs as its own grok session (``sessionId`` = the parent's
``subagentId``), so it becomes its own trace. Its events carry
``subagentType`` but not the parent session id; the parent link is the
``grok_build.subagent.id`` attribute on the parent's subagent span. No parent is
invented.

``PreToolUse`` is not mapped. It is the event that can deny a tool, grok
waits for it on every tool call, and pairing it with ``PostToolUse`` would
time the hook processes rather than the tool; ``durationMs`` is the tool's
own run time.

Never exported: ``cwd``, ``workspaceRoot``, ``transcriptPath`` (never
opened). Grok sends no model id, token counts, or cost in hook payloads.
Reason-like fields (stop reason, cancel source, end reason, start source,
permission mode, compaction trigger, signal) are exported only when they are
a short enum-like token; the ``StopFailure`` status message is one of grok's
documented error types (anything else reads ``unknown``). Free text, such as
``errorDetails``, a tool ``error`` or a denial ``reason``, is content.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from adapters.base import (
    END, ERROR, EVENT, INSTANT, OK, SESSION, START, SUBAGENT, TOOL, TURN, UPDATE,
    SpanEvent, compact, first, number,
)

APP = "grok_build"
DISPLAY_NAME = "Grok Build"
SERVICE_NAME = "grok-build"

# Documented ``StopFailure`` error types (bundled hooks guide, grok 1.0.52).
STOP_ERRORS = frozenset({"rate_limit", "authentication_failed", "invalid_request", "server_error",
                         "max_output_tokens", "unknown"})
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}")

# grok's own snake_case names (``hookEventName``) -> Claude-style names.
_PASCAL = {
    "session_start": "SessionStart", "session_end": "SessionEnd",
    "user_prompt_submit": "UserPromptSubmit", "pre_tool_use": "PreToolUse",
    "post_tool_use": "PostToolUse", "post_tool_use_failure": "PostToolUseFailure",
    "permission_denied": "PermissionDenied", "stop": "Stop",
    "stop_failure": "StopFailure", "stop_cancelled": "StopCancelled",
    "subagent_start": "SubagentStart", "subagent_stop": "SubagentStop",
    "pre_compact": "PreCompact", "post_compact": "PostCompact",
    "notification": "Notification",
}


def event_name(argv_event: Optional[str], payload: Dict[str, Any]) -> Optional[str]:
    if argv_event:
        return argv_event
    name = payload.get("hook_event_name")
    if name:
        return str(name)
    snake = payload.get("hookEventName")
    return _PASCAL.get(str(snake), str(snake)) if snake else None


def _token(value: Any) -> Optional[str]:
    """A vendor enum value (reason, source, mode, signal); free text is never metadata."""
    return value if isinstance(value, str) and _TOKEN.fullmatch(value) else None


def _base_attrs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return compact({
        "grok_build.permission_mode": _token(first(payload, "permissionMode", "permission_mode")),
        "grok_build.subagent.type": payload.get("subagentType"),
    })


def _tool_attrs(payload: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    return compact({
        **_base_attrs(payload),
        "grok_build.tool.name": tool_name,
        "grok_build.tool.duration_ms": number(payload.get("durationMs")),
        "grok_build.tool.input_truncated": payload.get("toolInputTruncated"),
        "grok_build.tool.result_truncated": payload.get("toolResultTruncated"),
        "grok_build.tool.backgrounded": payload.get("isBackgrounded"),
    })


def _shell_outcome(payload: Dict[str, Any]) -> Dict[str, Any]:
    """exit_code / timed_out / signal from a shell tool's result (metadata).

    Only read from a dict result: a truncated result arrives as a string.
    """
    result = first(payload, "toolResult", "tool_response")
    if not isinstance(result, dict):
        return {}
    exit_code = result.get("exit_code")
    signal = result.get("signal")
    return compact({
        "grok_build.tool.exit_code": exit_code if isinstance(exit_code, int) and not isinstance(exit_code, bool) else None,
        "grok_build.tool.timed_out": result.get("timed_out") if isinstance(result.get("timed_out"), bool) else None,
        "grok_build.tool.signal": signal if isinstance(signal, int) and not isinstance(signal, bool) else _token(signal),
    })


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    events = _parse(event, payload)
    subagent_type = payload.get("subagentType")
    if events and subagent_type and event != "SubagentStart":
        # Inside a subagent's own session (SubagentStart fires in the parent):
        # name its root from the first exported span on.
        events.append(SpanEvent(UPDATE, SESSION, events[0].session_id,
                                name=f"{DISPLAY_NAME} subagent session: {subagent_type}"))
    return events


def _parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    session = first(payload, "sessionId", "session_id")
    if not session:
        return []  # never invent a session id
    sid = str(session)
    prompt_id = first(payload, "promptId")
    turn = str(prompt_id) if prompt_id is not None else None

    if event == "SessionStart":
        return [SpanEvent(START, SESSION, sid, attributes=compact({
            **_base_attrs(payload),
            "grok_build.session.source": _token(payload.get("source")),
        }))]

    if event == "SessionEnd":
        subagent_type = payload.get("subagentType")
        return [SpanEvent(
            END, SESSION, sid,
            name=f"{DISPLAY_NAME} subagent session: {subagent_type}" if subagent_type else None,
            attributes=compact({
                **_base_attrs(payload),
                "grok_build.session.end_reason": _token(payload.get("reason")),
            }),
        )]

    if event == "UserPromptSubmit":
        if turn is None:
            return []
        return [SpanEvent(START, TURN, sid, key=turn, input=payload.get("prompt"),
                          attributes=compact({**_base_attrs(payload), "grok_build.prompt_id": turn}))]

    if event in ("Stop", "StopFailure", "StopCancelled", "SubagentStop"):
        # The session-end ``Stop`` has no promptId: it is not a turn end.
        if turn is None:
            return []
        if event == "SubagentStop" and payload.get("phase") not in (None, "gate"):
            return []
        failed = event == "StopFailure"
        cancelled = event == "StopCancelled"
        error_type = None
        if failed:
            raw = payload.get("error")
            error_type = raw if isinstance(raw, str) and raw in STOP_ERRORS else "unknown"
        return [SpanEvent(
            END, TURN, sid, key=turn,
            status=ERROR if failed else (None if cancelled else OK),
            status_message=error_type,
            output=None if (failed or cancelled) else payload.get("lastAssistantMessage"),
            error_message=payload.get("errorDetails") if failed else None,
            attributes=compact({
                **_base_attrs(payload),
                "grok_build.prompt_id": turn,
                "grok_build.stop.event": event,
                "grok_build.stop.reason": _token(payload.get("reason")),
                "grok_build.stop.error": error_type,
                "grok_build.stop.cancelled_by": _token(payload.get("cancelledBy")) if cancelled else None,
            }),
        )]

    if event in ("PostToolUse", "PostToolUseFailure", "PermissionDenied"):
        tool_name = str(first(payload, "toolName", "tool_name") or "tool")
        failed = event != "PostToolUse"
        denied = event == "PermissionDenied"
        shell = {} if failed else _shell_outcome(payload)
        exit_code = shell.get("grok_build.tool.exit_code")
        message = ("permission denied" if denied else "tool failed") if failed else None
        if shell.get("grok_build.tool.timed_out"):
            message = "timed out"
        elif exit_code not in (None, 0):
            message = f"exit code {exit_code}"
        outcome = "permission_denied" if denied else ("failure" if (failed or message) else "success")
        return [SpanEvent(
            END, TOOL, sid,
            key=str(first(payload, "toolUseId", "tool_use_id") or ""),
            name=tool_name,
            duration_ms=number(payload.get("durationMs")),
            status=ERROR if message else OK,
            status_message=message,
            input=first(payload, "toolInput", "tool_input"),
            output=None if failed else first(payload, "toolResult", "tool_response"),
            error_message=first(payload, "error", "reason") if failed else None,
            attributes=compact({
                **_tool_attrs(payload, tool_name),
                **shell,
                "grok_build.tool.outcome": outcome,
            }),
        )]

    if event == "SubagentStart":
        subagent_type = payload.get("subagentType") or "subagent"
        return [SpanEvent(
            INSTANT, SUBAGENT, sid,
            key=str(first(payload, "subagentId") or ""),
            name=f"Subagent: {subagent_type}",
            input=payload.get("description"),
            attributes=compact({
                **_base_attrs(payload),
                "grok_build.subagent.id": payload.get("subagentId"),
                "grok_build.subagent.type": subagent_type,
            }),
        )]

    if event == "PostCompact":
        return [SpanEvent(INSTANT, EVENT, sid, name="Context compaction", attributes=compact({
            **_base_attrs(payload),
            "grok_build.compaction.trigger": _token(payload.get("trigger")),
        }))]

    return []
