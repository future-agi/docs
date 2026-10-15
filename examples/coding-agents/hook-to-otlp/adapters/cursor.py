"""Cursor agent hooks -> normalized span events.

Payload shapes follow https://cursor.com/docs/hooks (read 2026-10-14):
every agent hook carries ``conversation_id`` (session), ``generation_id``
(changes with every user message, so it is the turn) and ``model`` /
``model_id``. ``sessionStart`` / ``sessionEnd`` carry ``session_id``, which
the docs define as the same value as ``conversation_id``.

Mapped events (all non-permission hooks, so the emitter never decides
whether Cursor may run something):

    sessionStart        -> session start (root span exported, re-exported later)
    beforeSubmitPrompt  -> turn start           prompt = content
    postToolUse         -> tool span            start = end - duration
    postToolUseFailure  -> tool span, ERROR     status message = failure_type
    subagentStop        -> subagent span        start = end - duration_ms
    afterAgentThought   -> llm span "Agent thought"
    afterAgentResponse  -> llm span "Agent response", turn output = content
    preCompact          -> event span "Context compaction" (counts only)
    stop                -> turn end, ERROR when status == "error"
    sessionEnd          -> session end, ERROR when reason == "error"

Never exported: ``user_email``, ``transcript_path`` (never opened),
``workspace_roots``, ``cwd``, attachment paths.

Observed on real Cursor 3.24.18 payloads (not in the docs):

- ``afterAgentResponse`` and ``stop`` carry ``input_tokens``, ``output_tokens``,
  ``cache_read_tokens``, ``cache_write_tokens`` for the turn. They go on the
  "Agent response" LLM span as standard token counts (the turn keeps them as
  ``cursor.usage.*`` so trace totals are not counted twice).
- ``tool_use_id`` can be two ids joined by a newline (Cursor's ``call-...``
  id, then the provider's function-call id). The first line is the call id;
  the second is kept as ``cursor.tool.provider_call_id``.
- ``afterAgentThought`` fires twice per thinking block, once with a
  ``generation_id`` suffixed ``-<n>-<4 chars>``. Suffixes are stripped and the
  pair maps to one span id.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

from adapters.base import (
    END, ERROR, EVENT, INSTANT, LLM, OK, SESSION, START, SUBAGENT, TOOL, TURN,
    UPDATE, SpanEvent, compact, first, number,
)

APP = "cursor"
DISPLAY_NAME = "Cursor"
SERVICE_NAME = "cursor"

# Cursor blocks permission hooks on invalid output; this emitter is not
# meant to be wired to them, and answers neutrally if it is.
PERMISSION_HOOKS = {
    "preToolUse", "beforeShellExecution", "beforeMCPExecution",
    "beforeReadFile", "beforeTabFileRead", "subagentStart",
}


def event_name(argv_event: Optional[str], payload: Dict[str, Any]) -> Optional[str]:
    return argv_event or payload.get("hook_event_name")


def respond(event: str, payload: Dict[str, Any]) -> str:
    if event == "beforeSubmitPrompt":
        return '{"continue": true}'
    if event in PERMISSION_HOOKS:
        return '{"permission": "allow"}'
    return "{}"


def resource_attributes(event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return compact({"coding_agent.app.version": payload.get("cursor_version")})


def _model(payload: Dict[str, Any]) -> Optional[str]:
    value = first(payload, "model_id", "model")
    return str(value) if value is not None else None


def _model_params(payload: Dict[str, Any]) -> Dict[str, Any]:
    params = payload.get("model_params")
    out: Dict[str, Any] = {}
    if isinstance(params, list):
        for item in params:
            if isinstance(item, dict) and item.get("id") and item.get("value") is not None:
                out[f"cursor.model_params.{item['id']}"] = str(item["value"])
    if payload.get("model") and payload.get("model_id") and payload["model"] != payload["model_id"]:
        out["cursor.model"] = str(payload["model"])
    return out


_SUFFIXED_GENERATION = re.compile(
    r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-\d+-[a-z0-9]{4}$")


def _generation(payload: Dict[str, Any]) -> Optional[str]:
    """The turn id: ``generation_id`` without Cursor's per-phase suffix."""
    gen = first(payload, "generation_id")
    if gen is None:
        return None
    gen = str(gen)
    match = _SUFFIXED_GENERATION.match(gen)
    return match.group(1) if match else gen


def _usage(payload: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    tokens_in = payload.get("input_tokens")
    tokens_out = payload.get("output_tokens")
    if not isinstance(tokens_in, int) and not isinstance(tokens_out, int):
        return {}
    usage: Dict[str, Any] = {}
    if prefix == "llm":
        usage = {
            "llm.token_count.prompt": tokens_in,
            "llm.token_count.completion": tokens_out,
            "llm.token_count.prompt_details.cache_read": payload.get("cache_read_tokens"),
            "llm.token_count.prompt_details.cache_write": payload.get("cache_write_tokens"),
        }
        if isinstance(tokens_in, int) and isinstance(tokens_out, int):
            usage["llm.token_count.total"] = tokens_in + tokens_out
    else:
        for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            usage[f"cursor.usage.{key}"] = payload.get(key)
    return compact(usage)


def _tool_call_ids(payload: Dict[str, Any]) -> "tuple[str, Optional[str]]":
    """(call id, provider call id) from a possibly newline-joined ``tool_use_id``."""
    raw = first(payload, "tool_use_id")
    if raw is None:
        return "", None
    parts = [part.strip() for part in str(raw).splitlines() if part.strip()]
    if not parts:
        return "", None
    return parts[0], (parts[1] if len(parts) > 1 else None)


def _digest(*parts: Any) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def parse(event: str, payload: Dict[str, Any]) -> List[SpanEvent]:
    session = first(payload, "conversation_id", "session_id")
    if not session:
        return []  # R-01: never invent a session id
    sid = str(session)
    turn = _generation(payload)
    model = _model(payload)

    if event == "sessionStart":
        return [SpanEvent(START, SESSION, sid, model=model, attributes=compact({
            "cursor.composer_mode": payload.get("composer_mode"),
            "cursor.is_background_agent": payload.get("is_background_agent"),
        }))]

    if event == "sessionEnd":
        reason = payload.get("reason")
        failed = reason == "error"
        return [SpanEvent(
            END, SESSION, sid,
            duration_ms=number(payload.get("duration_ms")),
            status=ERROR if failed else OK,
            status_message="session ended with error" if failed else None,
            error_message=payload.get("error_message") if failed else None,
            attributes=compact({
                "cursor.session.reason": reason,
                "cursor.session.final_status": payload.get("final_status"),
                "cursor.session.duration_ms": number(payload.get("duration_ms")),
                "cursor.is_background_agent": payload.get("is_background_agent"),
            }),
        )]

    if event == "beforeSubmitPrompt":
        if turn is None:
            return []
        attachments = payload.get("attachments")
        return [SpanEvent(
            START, TURN, sid, key=turn, model=model, input=payload.get("prompt"),
            attributes=compact({
                "cursor.generation_id": turn,
                "cursor.attachments.count": len(attachments) if isinstance(attachments, list) else None,
                **_model_params(payload),
            }),
        )]

    if event == "stop":
        if turn is None:
            return []
        status = payload.get("status")
        failed = status == "error"
        return [SpanEvent(
            END, TURN, sid, key=turn, model=model,
            status=ERROR if failed else OK,
            status_message="agent loop ended with error" if failed else None,
            attributes=compact({
                "cursor.generation_id": turn,
                "cursor.stop.status": status,
                "cursor.loop_count": payload.get("loop_count"),
                **_model_params(payload),
                **_usage(payload, "turn"),
            }),
        )]

    if event in ("postToolUse", "postToolUseFailure"):
        tool_name = str(first(payload, "tool_name") or "tool")
        failed = event == "postToolUseFailure"
        failure_type = payload.get("failure_type") if failed else None
        call_id, provider_call_id = _tool_call_ids(payload)
        return [SpanEvent(
            END, TOOL, sid,
            key=call_id,
            turn_id=turn,
            name=tool_name,
            duration_ms=number(payload.get("duration")),
            status=ERROR if failed else OK,
            status_message=str(failure_type or "error") if failed else None,
            input=payload.get("tool_input"),
            output=None if failed else payload.get("tool_output"),
            error_message=payload.get("error_message") if failed else None,
            attributes=compact({
                "cursor.tool.name": tool_name,
                "cursor.tool.provider_call_id": provider_call_id,
                "cursor.tool.duration_ms": number(payload.get("duration")),
                "cursor.tool.failure_type": failure_type,
                "cursor.tool.is_interrupt": payload.get("is_interrupt") if failed else None,
            }),
        )]

    if event == "subagentStop":
        subagent_type = payload.get("subagent_type") or "subagent"
        status = payload.get("status")
        failed = status == "error"
        modified = payload.get("modified_files")
        return [SpanEvent(
            END, SUBAGENT, sid,
            key=_digest(subagent_type, payload.get("task"), payload.get("description")),
            turn_id=turn,
            name=f"Subagent: {subagent_type}",
            duration_ms=number(payload.get("duration_ms")),
            status=ERROR if failed else OK,
            status_message="subagent ended with error" if failed else None,
            input=payload.get("task"),
            output=payload.get("summary"),
            attributes=compact({
                "cursor.subagent.type": subagent_type,
                "cursor.subagent.status": status,
                "cursor.subagent.message_count": payload.get("message_count"),
                "cursor.subagent.tool_call_count": payload.get("tool_call_count"),
                "cursor.subagent.modified_files.count": len(modified) if isinstance(modified, list) else None,
                "cursor.subagent.duration_ms": number(payload.get("duration_ms")),
            }),
        )]

    if event == "afterAgentThought":
        text = payload.get("text")
        return [SpanEvent(
            INSTANT, LLM, sid, turn_id=turn, name="Agent thought", model=model,
            key=_digest("thought", turn, payload.get("duration_ms"),
                        hashlib.sha256(str(text).encode("utf-8", "replace")).hexdigest()),
            duration_ms=number(payload.get("duration_ms")),
            output=payload.get("text"),
            attributes=compact({"cursor.llm.part": "thought", **_model_params(payload)}),
        )]

    if event == "afterAgentResponse":
        events = [SpanEvent(
            INSTANT, LLM, sid, turn_id=turn, name="Agent response", model=model,
            output=payload.get("text"),
            attributes=compact({"cursor.llm.part": "response", **_model_params(payload),
                                **_usage(payload, "llm")}),
        )]
        if turn is not None:
            events.append(SpanEvent(UPDATE, TURN, sid, key=turn, output=payload.get("text")))
        return events

    if event == "preCompact":
        return [SpanEvent(
            INSTANT, EVENT, sid, turn_id=turn, name="Context compaction",
            attributes=compact({
                "cursor.compaction.trigger": payload.get("trigger"),
                "cursor.compaction.context_usage_percent": number(payload.get("context_usage_percent")),
                "cursor.compaction.context_tokens": payload.get("context_tokens"),
                "cursor.compaction.context_window_size": payload.get("context_window_size"),
                "cursor.compaction.message_count": payload.get("message_count"),
                "cursor.compaction.messages_to_compact": payload.get("messages_to_compact"),
                "cursor.compaction.is_first": payload.get("is_first_compaction"),
            }),
        )]

    return []
