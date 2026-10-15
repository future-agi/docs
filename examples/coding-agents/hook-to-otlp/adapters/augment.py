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

    SessionStart  -> opens the session (the root span is sent with the first
                     child span; an empty session exports nothing)
    PostToolUse   -> tool span (ERROR when tool_error is set)
                     tool_input / tool_output / tool_error = content
    Stop          -> event span "Agent stop" (ERROR when the cause is
                     "error"); the last cause is also kept on the session
    SessionEnd    -> session end

``PreToolUse`` is deliberately not registered or mapped: it is the hook that
can block a tool, and tracing never takes part in approving or blocking. As a
result tool spans have no measured duration.

``Stop`` carries ``agent_stop_cause``: ``end_turn``, ``interrupted``,
``max_iterations``, ``error`` (documented) and ``empty_completion`` (0.36.0,
undocumented). Every cause is recorded as-is; only ``error`` sets ERROR.

Never exported, even with content capture on: ``workspace_roots``, the
``context`` object (``includeUserContext``: user email, model display name),
the ``conversation`` object (``includeConversationData``), ``user_prompt``
(0.36.0 adds it to tool events when ``includeConversationData`` is on),
``_exchange`` (0.36.0 passes this internal object on ``Stop``),
``mcp_metadata``, and file paths and contents from ``file_changes`` (only the
count and change types). MCP tool names are ``<tool>_<server>``, so the MCP
server name is exported as part of the tool name.

With content capture off, a tool error exports only the fixed status message
``tool error``; the ``tool_error`` text is content.
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
