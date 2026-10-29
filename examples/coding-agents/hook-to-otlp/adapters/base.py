"""Adapter contract for the hook-to-OTLP emitter.

An adapter is a plain module ``adapters/<app>.py``. It never does I/O: it
receives the hook event name and the parsed stdin payload and returns
normalized ``SpanEvent`` records. The emitter core (``emit.py``) owns state,
span ids, parenting, durations, privacy, and export.

Required module attributes::

    APP: str            # slug, equal to the module name ("cursor")
    DISPLAY_NAME: str   # used in default span names ("Cursor session")

    def parse(event: str, payload: dict) -> list[SpanEvent]:
        ...

Optional module attributes::

    SERVICE_NAME: str   # OTel resource service.name (default: APP)

    def event_name(argv_event: str | None, payload: dict) -> str | None:
        # default: argv_event, else payload["hook_event_name"]

    def respond(event: str, payload: dict) -> str:
        # what the host app expects on stdout; default "{}"

    def resource_attributes(event: str, payload: dict) -> dict:
        # extra resource attributes, e.g. the app version; metadata only

Rules for adapters:

* Return ``[]`` for events you do not map, and when the payload has no
  session id. Never invent a session id.
* Put content (prompts, tool arguments, tool results, model text, error
  text) ONLY in ``input``, ``output`` and ``error_message``. The core drops
  them unless the user opts in with ``FI_HOOK_CAPTURE_CONTENT=1``.
* ``attributes`` and ``status_message`` are always exported: put only
  metadata there (ids, names, counts, durations, enum-like statuses). Never
  emails, paths, transcript locations, or free text.
* Never open files named in the payload (for example ``transcript_path``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Scopes: what the span represents. The core parents them as
# session -> turn -> (tool | subagent | llm | event).
SESSION = "session"
TURN = "turn"
TOOL = "tool"
SUBAGENT = "subagent"
LLM = "llm"
EVENT = "event"
SCOPES = (SESSION, TURN, TOOL, SUBAGENT, LLM, EVENT)

# Phases: how the hook relates to the span's lifetime.
START = "start"      # opens a span; nothing is exported until it ends
END = "end"          # closes (and exports) a span
INSTANT = "instant"  # a complete span in one hook (start = end - duration_ms)
UPDATE = "update"    # merges attributes/content into an open span
PHASES = (START, END, INSTANT, UPDATE)

OK = "ok"
ERROR = "error"


@dataclass
class SpanEvent:
    """One normalized hook observation.

    ``key`` pairs START/END/UPDATE events of the same scope inside a session
    (turn id, tool call id, subagent id). Leave it empty for the session
    scope, and for INSTANT/END events that have no stable id (the core then
    makes the span unique).

    ``turn_id`` names the parent turn of tool/subagent/llm/event spans. When
    it is None the core uses the session's currently open turn, or parents
    the span directly under the session.
    """

    phase: str
    scope: str
    session_id: str
    key: str = ""
    turn_id: Optional[str] = None
    name: Optional[str] = None
    kind: Optional[str] = None  # fi.span.kind; default derived from scope
    attributes: Dict[str, Any] = field(default_factory=dict)
    model: Optional[str] = None
    duration_ms: Optional[float] = None
    status: Optional[str] = None  # OK | ERROR | None (unset)
    status_message: Optional[str] = None  # metadata only, e.g. "timeout"
    # Content. Exported only when FI_HOOK_CAPTURE_CONTENT is on.
    input: Any = None
    output: Any = None
    error_message: Any = None


def first(payload: Dict[str, Any], *keys: str) -> Any:
    """First non-empty value among ``keys`` in ``payload``, else None."""
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def number(value: Any) -> Optional[float]:
    """``value`` as a float when it is numeric (bools excluded), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def compact(attributes: Dict[str, Any]) -> Dict[str, Any]:
    """Drop None/empty values so adapters can build attribute dicts inline."""
    return {k: v for k, v in attributes.items() if v not in (None, "", [], {})}
