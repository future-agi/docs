"""Synthetic OTLP/HTTP protobuf fixture shaped like the API spans that the
Claude API sends to a telemetry destination for a Managed Agents session.

STANDIN. Nothing here came from Anthropic's servers. Span names, kinds,
resource, scope and attribute keys follow Anthropic's published span reference
(https://platform.claude.com/docs/en/api/opentelemetry/spans, read 2026-10-16).
Values (ids, model, token counts) are made up.

Two content modes, as a destination has:
  metadata_only  (Anthropic's default) - no gen_ai.*.messages / tool payloads
  content        (opt-in "Full content") - adds them, carrying MARKER
"""
from __future__ import annotations

import json
import os
import secrets
import time

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span, Status

SERVER = Span.SpanKind.SPAN_KIND_SERVER
INTERNAL = Span.SpanKind.SPAN_KIND_INTERNAL


def _kv(key: str, value) -> KeyValue:
    if isinstance(value, bool):
        return KeyValue(key=key, value=AnyValue(bool_value=value))
    if isinstance(value, int):
        return KeyValue(key=key, value=AnyValue(int_value=value))
    return KeyValue(key=key, value=AnyValue(string_value=str(value)))


class _Builder:
    def __init__(self, base_ns: int):
        self.spans: list[Span] = []
        self.t = base_ns

    def span(self, trace_id: bytes, parent: bytes | None, name: str, kind, dur_ms: int, attrs: dict,
             error: str | None = None, offset_ms: int = 0) -> bytes:
        sid = secrets.token_bytes(8)
        start = self.t + offset_ms * 1_000_000
        sp = Span(
            trace_id=trace_id,
            span_id=sid,
            parent_span_id=parent or b"",
            name=name,
            kind=kind,
            start_time_unix_nano=start,
            end_time_unix_nano=start + dur_ms * 1_000_000,
            attributes=[_kv(k, v) for k, v in attrs.items()],
            status=Status(code=Status.STATUS_CODE_ERROR, message=error) if error
            else Status(code=Status.STATUS_CODE_OK),
        )
        self.spans.append(sp)
        return sid


def build(content_mode: str, marker: str, *, failure: bool = False, project_name: str | None = None,
          session_id: str | None = None) -> tuple[ExportTraceServiceRequest, dict]:
    """Return (request, meta). meta has trace ids and the session id."""
    assert content_mode in ("metadata_only", "content")
    content = content_mode == "content"
    now = time.time_ns() - 30 * 1_000_000_000
    b = _Builder(now)
    trace_id = secrets.token_bytes(16)
    session_id = session_id or "sesn_" + secrets.token_hex(12)
    thread_id = "sthr_" + secrets.token_hex(12)
    common = {
        "gen_ai.provider.name": "anthropic",
        "anthropic.organization.id": "org_fixture0000000000",
        "anthropic.workspace.id": "wrkspc_fixture000000000",
    }
    session_attrs = {"anthropic.session.id": session_id, "gen_ai.conversation.id": thread_id}
    model = "claude-opus-5-5"

    send = b.span(trace_id, None, "anthropic.sessions.events.send", SERVER, 120 if not failure else 90, {
        **common,
        "anthropic.request.id": "req_" + secrets.token_hex(12),
        "anthropic.session.id": session_id,
        "http.request.method": "POST",
        "http.route": "/v1/sessions/{session_id}/events",
        "http.response.status_code": 200,
        "server.address": "api.anthropic.com",
        "server.port": 443,
        "url.scheme": "https",
        "url.path": f"/v1/sessions/{session_id}/events",
        "url.full": f"https://api.anthropic.com/v1/sessions/{session_id}/events",
    })

    user_text = f"List the files in the repo and count them. {marker}"
    turn_attrs = {
        **common, **session_attrs,
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.id": "agent_fixture000000000",
        "gen_ai.agent.name": "repo-helper",
        "gen_ai.request.model": model,
    }
    if failure:
        turn_attrs["error.type"] = "rate_limit_error"
    else:
        turn_attrs["anthropic.session.turn.stop_reason"] = "end_turn"
    if content:
        turn_attrs["gen_ai.system_instructions"] = json.dumps(
            [{"type": "text", "content": f"You help with repositories. {marker}"}])
        turn_attrs["gen_ai.input.messages"] = json.dumps(
            [{"role": "user", "parts": [{"type": "text", "content": user_text}]}])
        if not failure:
            turn_attrs["gen_ai.output.messages"] = json.dumps([{
                "role": "assistant",
                "parts": [
                    {"type": "tool_call", "id": "sevt_fixture_tool_1", "name": "bash",
                     "arguments": {"command": f"ls | wc -l  # {marker}"}},
                    {"type": "tool_call_response", "id": "sevt_fixture_tool_1", "response": f"7 {marker}"},
                    {"type": "text", "content": f"The repo has 7 files. {marker}"},
                ],
                "finish_reason": "end_turn",
            }])
    turn = b.span(trace_id, send, "anthropic.session.turn", INTERNAL, 4200 if not failure else 800, turn_attrs,
                  error=("turn failed: rate_limit_error" if failure else None), offset_ms=20)

    mr1 = {**common, **session_attrs, "gen_ai.operation.name": "chat", "gen_ai.request.model": model,
           "gen_ai.usage.input_tokens": 1834, "gen_ai.usage.output_tokens": 41,
           "gen_ai.usage.cache_read.input_tokens": 1200, "gen_ai.usage.cache_write.input_tokens": 0}
    if failure:
        mr1 = {**common, **session_attrs, "gen_ai.operation.name": "chat", "gen_ai.request.model": model,
               "error.type": "rate_limit_error"}
        b.span(trace_id, turn, "anthropic.model_request", INTERNAL, 700, mr1,
               error="model request failed: rate_limit_error", offset_ms=40)
    else:
        b.span(trace_id, turn, "anthropic.model_request", INTERNAL, 1600, mr1, offset_ms=40)
        tool = {**common, **session_attrs, "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "bash",
                "gen_ai.tool.call.id": "sevt_fixture_tool_1", "anthropic.tool.evaluated_permission": "allow"}
        if content:
            tool["gen_ai.tool.call.arguments"] = json.dumps({"command": f"ls | wc -l  # {marker}"})
            tool["anthropic.tool_result.content"] = json.dumps([{"type": "text", "text": f"7 {marker}"}])
        b.span(trace_id, turn, "anthropic.tool_use bash", INTERNAL, 900, tool, offset_ms=1700)
        mr2 = {**common, **session_attrs, "gen_ai.operation.name": "chat", "gen_ai.request.model": model,
               "gen_ai.usage.input_tokens": 1907, "gen_ai.usage.output_tokens": 18,
               "gen_ai.usage.cache_read.input_tokens": 1800, "gen_ai.usage.cache_write.input_tokens": 0}
        b.span(trace_id, turn, "anthropic.model_request", INTERNAL, 1500, mr2, offset_ms=2650)

    res_attrs = [_kv("service.name", "claude-platform")]
    if project_name:  # what a resource processor in front of Future AGI would add
        res_attrs.append(_kv("project_name", project_name))
    req = ExportTraceServiceRequest(resource_spans=[ResourceSpans(
        resource=Resource(attributes=res_attrs),
        scope_spans=[ScopeSpans(scope=InstrumentationScope(name="com.anthropic.claude-platform"), spans=b.spans)],
    )])
    return req, {"trace_id": trace_id.hex(), "session_id": session_id, "spans": len(b.spans),
                 "content_mode": content_mode, "failure": failure}


def add_project_name(req: ExportTraceServiceRequest, project_name: str) -> ExportTraceServiceRequest:
    """The one transform a collector/relay in front of Future AGI must apply."""
    out = ExportTraceServiceRequest()
    out.CopyFrom(req)
    for rs in out.resource_spans:
        keys = {a.key for a in rs.resource.attributes}
        if "project_name" not in keys:
            rs.resource.attributes.append(_kv("project_name", project_name))
    return out


if __name__ == "__main__":
    r, m = build(os.environ.get("MODE", "metadata_only"), "MARKER")
    print(m, len(r.SerializeToString()))
