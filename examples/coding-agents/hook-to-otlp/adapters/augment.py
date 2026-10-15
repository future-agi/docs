"""Augment Code (Auggie CLI) hooks -> normalized span events.

Payload shapes follow https://docs.augmentcode.com/cli/hooks (read
2026-10-14): every event carries ``hook_event_name``, ``conversation_id``
(the session) and ``workspace_roots``. Tool events carry ``tool_name``,
``tool_input`` and ``is_mcp_tool``; ``PostToolUse`` adds ``tool_output``,
``tool_error`` and ``file_changes``. ``Stop`` carries ``agent_stop_cause``.
Auggie sends no turn id, no tool call id, no tool timing, no model id and
no token counts, so this adapter does not produce turn spans and tool spans
have no measured duration.

Mapped events:

    SessionStart  -> session start (root span exported, re-exported later)
    PostToolUse   -> tool span (ERROR when tool_error is set)
                     tool_input / tool_output / tool_error = content
    Stop          -> event span "Agent stop" (ERROR when the cause is
                     "error"); the last cause is also kept on the session
    SessionEnd    -> session end

``PreToolUse`` is not mapped: without a tool call id it cannot be paired
with ``PostToolUse``, and it is the one hook that can block a tool.

Never exported, even with content capture on: ``workspace_roots``, the
``context`` object (``includeUserContext``: user email, model display name),
the ``conversation`` object (``includeConversationData``), ``mcp_metadata``,
and file contents from ``file_changes`` (only the count and change types).
"""
from __future__ import annotations

from typing import Any, Dict, List

from adapters.base import (
    END, ERROR, EVENT, INSTANT, OK, SESSION, START, TOOL, UPDATE,
    SpanEvent, compact, first,
)

APP = "augment"
DISPLAY_NAME = "Auggie"
SERVICE_NAME = "auggie-cli"


def _file_change_attrs(payload: Dict[str, Any]) -> Dict[str, Any]:
    changes = payload.get("file_changes")
    if not isinstance(changes, list):
        return {}
    types = sorted({str(c.get("changeType")) for c in changes if isinstance(c, dict) and c.get("changeType")})
    return compact({
        "augment.tool.file_changes.count": len(changes),
        "augment.tool.file_changes.types": types,
    })


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    session = first(payload, "conversation_id")
    if not session:
        return []  # R-01: never invent a session id
    sid = str(session)

    if event == "SessionStart":
        return [SpanEvent(START, SESSION, sid)]

    if event == "SessionEnd":
        return [SpanEvent(END, SESSION, sid)]

    if event == "PostToolUse":
        tool_name = str(first(payload, "tool_name") or "tool")
        error = payload.get("tool_error")
        failed = error not in (None, "")
        return [SpanEvent(
            END, TOOL, sid,
            name=tool_name,
            status=ERROR if failed else OK,
            status_message="tool error" if failed else None,
            input=payload.get("tool_input"),
            output=None if failed else payload.get("tool_output"),
            error_message=error if failed else None,
            attributes=compact({
                "augment.tool.name": tool_name,
                "augment.tool.is_mcp": payload.get("is_mcp_tool"),
                **_file_change_attrs(payload),
            }),
        )]

    if event == "Stop":
        cause = payload.get("agent_stop_cause")
        failed = cause == "error"
        return [
            SpanEvent(
                INSTANT, EVENT, sid, name="Agent stop",
                status=ERROR if failed else OK,
                status_message="agent stopped with error" if failed else None,
                attributes=compact({"augment.stop.cause": cause}),
            ),
            SpanEvent(UPDATE, SESSION, sid, attributes=compact({"augment.stop.last_cause": cause})),
        ]

    return []
