"""Devin Desktop Cascade hooks -> normalized span events.

Payload shapes follow https://docs.devin.ai/desktop/cascade/hooks (read
2026-10-14). Every Cascade hook carries ``agent_action_name`` (the event),
``trajectory_id`` (the Cascade conversation), ``execution_id`` (one agent
turn), ``timestamp``, ``model_name`` (the model selector's display label,
"Unknown" when not known) and an event-specific ``tool_info`` object.
Cascade has no session start/end hook (the session span is sent along
with every turn and tool span), no tool call id, no tool timing and no
token counts.

Mapped events:

    pre_user_prompt        -> turn start (key execution_id)  user_prompt = content
    post_read_code         -> tool span "read_code"          file_path = content
    post_write_code        -> tool span "write_code"         file_path, edits = content
    post_run_command       -> tool span "run_command"        command_line, cwd = content
    post_mcp_tool_use      -> tool span named by mcp_tool_name
                              mcp_tool_arguments / mcp_result = content
    post_cascade_response  -> turn end                       response = content

Pre-hooks other than ``pre_user_prompt`` (they can block an action and
carry no id to pair them with the post-hook) and ``post_setup_worktree``
are not mapped. ``post_cascade_response_with_transcript`` is never mapped
and its ``transcript_path`` is never opened. This adapter covers Cascade
only, not the Devin Local agent or hosted Devin sessions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.base import END, OK, START, TOOL, TURN, SpanEvent, compact, first

APP = "devin_desktop"
DISPLAY_NAME = "Cascade"
SERVICE_NAME = "devin-desktop"

TOOL_EVENTS = {
    "post_read_code": "read_code",
    "post_write_code": "write_code",
    "post_run_command": "run_command",
    "post_mcp_tool_use": "mcp_tool",
}


def event_name(argv_event: Optional[str], payload: Dict[str, Any]) -> Optional[str]:
    return argv_event or payload.get("agent_action_name")


def _model(payload: Dict[str, Any]) -> Optional[str]:
    label = payload.get("model_name")
    return str(label) if label not in (None, "", "Unknown") else None


def _common(event: str, payload: Dict[str, Any], turn: Optional[str]) -> Dict[str, Any]:
    return compact({
        "devin_desktop.action": event,
        "devin_desktop.execution_id": turn,
        # A display label ("Claude Sonnet 4"), not a stable model id.
        "devin_desktop.model_label": _model(payload),
    })


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    trajectory = first(payload, "trajectory_id")
    if not trajectory:
        return []  # R-01: never invent a session id
    sid = str(trajectory)
    execution = first(payload, "execution_id")
    turn = str(execution) if execution is not None else None
    info = payload.get("tool_info") if isinstance(payload.get("tool_info"), dict) else {}
    model = _model(payload)

    if event == "pre_user_prompt":
        if turn is None:
            return []
        return [SpanEvent(START, TURN, sid, key=turn, model=model, input=info.get("user_prompt"),
                          attributes=_common(event, payload, turn))]

    if event == "post_cascade_response":
        if turn is None:
            return []
        return [SpanEvent(END, TURN, sid, key=turn, model=model, status=OK,
                          output=info.get("response"), attributes=_common(event, payload, turn))]

    if event in TOOL_EVENTS:
        name = TOOL_EVENTS[event]
        attributes = _common(event, payload, turn)
        tool_input: Any = None
        output: Any = None
        if event == "post_read_code":
            tool_input = {"file_path": info.get("file_path")}
        elif event == "post_write_code":
            edits = info.get("edits")
            tool_input = {"file_path": info.get("file_path"), "edits": edits}
            attributes["devin_desktop.write.edit_count"] = len(edits) if isinstance(edits, list) else None
        elif event == "post_run_command":
            tool_input = {"command_line": info.get("command_line"), "cwd": info.get("cwd")}
        else:
            name = str(info.get("mcp_tool_name") or name)
            attributes["devin_desktop.mcp.server"] = info.get("mcp_server_name")
            attributes["devin_desktop.mcp.tool"] = info.get("mcp_tool_name")
            tool_input = info.get("mcp_tool_arguments")
            output = info.get("mcp_result")
        return [SpanEvent(END, TOOL, sid, turn_id=turn, name=name, status=OK,
                          input=tool_input, output=output, attributes=compact(attributes))]

    return []
