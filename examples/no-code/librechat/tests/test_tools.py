"""Unit tests for the test-run helpers: chat driver, env renderer, stored-span checks, privacy scanner."""
import json
import os
import stat

import pytest

import check_spans
import drive_chat
import render_env
import scan_local_stack


# ---- drive_chat ------------------------------------------------------------------------------------------

def test_build_turn_matches_the_web_ui_body():
    body = drive_chat.build_turn("hi", "TestModels", "gpt-6-luna", ["order-tools"])
    assert body["endpoint"] == "TestModels" and body["endpointType"] == "custom"
    assert body["model"] == "gpt-6-luna"
    assert body["ephemeralAgent"] == {"mcp": ["order-tools"]}
    assert body["parentMessageId"] == drive_chat.ROOT_PARENT
    assert body["generationProtocolVersion"] == 2
    assert "conversationId" not in body
    follow = drive_chat.build_turn("again", "TestModels", "m", conversation_id="c1", parent_message_id="p1")
    assert follow["conversationId"] == "c1" and follow["parentMessageId"] == "p1"


def test_parse_sse_reads_data_lines_only():
    lines = [b"event: message\n", b'data: {"a": 1}\n', b"\n", b"data: not json\n", b'data: {"final": true}\n']
    assert list(drive_chat.parse_sse(lines)) == [{"a": 1}, {"final": True}]


def test_summarize_tool_turn():
    events = [
        {"event": "on_token_usage", "data": {"input_tokens": 1}},
        {"event": "on_run_step_completed", "data": {"result": {"tool_call": {"name": "get_order_status_mcp_order-tools"}}}},
        {"final": True, "conversation": {"conversationId": "c"},
         "responseMessage": {"messageId": "m", "content": [{"type": "tool_call"}, {"type": "text", "text": "done"}]}},
    ]
    out = drive_chat.summarize(events)
    assert out["final"] and not out["error"]
    assert out["tool_calls"] == ["get_order_status_mcp_order-tools"]
    assert out["text"] == "done" and out["conversation_id"] == "c" and out["usage_events"] == 1


def test_summarize_failed_turn_is_an_error():
    events = [{"final": True, "responseMessage": {"content": [{"type": "error", "error": "provider failed"}]}}]
    assert drive_chat.summarize(events)["error"] is True


def test_browser_user_agent_is_recognised_by_librechat():
    # LibreChat's uaParser rejects clients whose user agent names no browser ("Illegal request").
    assert "Chrome/" in drive_chat.BROWSER_UA and drive_chat.BROWSER_UA.startswith("Mozilla/5.0")


# ---- render_env ------------------------------------------------------------------------------------------

ENV = {"FI_API_KEY": "k-123", "FI_SECRET_KEY": "s-456", "TEST_LLM_BASE_URL": "http://llm/v1",
       "TEST_LLM_API_KEY": "llm-key", "TEST_LLM_MODEL": "model-x"}


def test_render_env_fills_placeholders_and_keeps_files_private(tmp_path, monkeypatch, capsys):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    render_env.main(["render_env.py", str(tmp_path)])
    env_text = (tmp_path / "librechat.env").read_text()
    assert "LANGFUSE_PUBLIC_KEY=k-123" in env_text and "LANGFUSE_SECRET_KEY=s-456" in env_text
    assert "X-Api-Key=k-123,X-Secret-Key=s-456" in env_text
    assert "YOUR_" not in env_text
    assert stat.S_IMODE(os.stat(tmp_path / "librechat.env").st_mode) == 0o600
    assert "default: ['model-x', 'th8234-missing-model']" in (tmp_path / "librechat.yaml").read_text()
    assert "s-456" not in capsys.readouterr().out


def test_render_env_requires_keys(tmp_path, monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit):
        render_env.main(["render_env.py", str(tmp_path)])


def test_render_block_rejects_unknown_placeholder():
    with pytest.raises(SystemExit):
        render_env.render_block("A=YOUR_OTHER_THING\n", ENV)


# ---- check_spans -----------------------------------------------------------------------------------------

def _row(name, kind, **kw):
    row = {"trace_id": "t", "id": name, "parent_span_id": kw.pop("parent", "p"), "name": name,
           "observation_type": kind, "status": "UNSET", "status_message": "", "model": "",
           "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "session": "s1",
           "end_user": "u1", "attrs_string": {}}
    row.update(kw)
    return row


GOOD = [
    _row("AgentGraph", "agent", parent=""),
    _row("llm", "llm", model="gpt-6-luna", prompt_tokens=10, completion_tokens=5),
    _row("tool-dispatch", "tool", attrs_string={"tool.name": "get_order_status"}),
    _row("llm-failed", "llm", status="ERROR", status_message="error"),
    _row("POST /api/agents/chat/:endpoint", "unknown", parent="", session="", end_user=""),
    _row("librechat.sse.stream", "unknown", session="", end_user=""),
]


def test_check_spans_passes_on_the_expected_shape():
    checks, summary = check_spans.evaluate(GOOD, "gpt-6-luna", expect_error=True, expect_backend=True)
    assert all(checks.values()), checks
    assert summary["tools"] == ["get_order_status"]


def test_check_spans_fails_without_tokens_or_tool_name():
    rows = [r for r in GOOD if r["observation_type"] != "tool"]
    rows[1] = dict(rows[1], prompt_tokens=0)
    checks, _ = check_spans.evaluate(rows, "gpt-6-luna")
    assert not checks["llm tokens set"] and not checks["tool span with tool.name"]


def test_check_spans_flags_background_roots():
    rows = GOOD + [_row("mongoose.AgentTriggerDelivery.find", "unknown", parent="", session="", end_user="")]
    checks, _ = check_spans.evaluate(rows, expect_backend=True)
    assert not checks["no parentless background database spans"]


# ---- scan_local_stack ------------------------------------------------------------------------------------

def test_parse_needle_hides_labelled_values():
    assert scan_local_stack.parse_needle("fi_secret=abc123") == ("fi_secret", "abc123")
    label, value = scan_local_stack.parse_needle("A-very-long-unlabelled-needle-value")
    assert value == "A-very-long-unlabelled-needle-value" and label != value


def test_count_needle_matches_json_escaped_paths():
    blobs = {"t1": json.dumps({"p": "/Users/me/x"}).replace("/", "\\/"), "t2": "nothing"}
    assert scan_local_stack.count_needle(blobs, "/Users/me") == {"t1": 1}


def test_attribute_keys_reads_maps_and_resource_json():
    rows = [{"name": "llm", "attrs_string": {"a": "1"}, "attrs_number": {"b": 2}, "attrs_bool": {},
             "resource_attrs": {"project_name": "p", "service": {"name": "librechat"}}}]
    keys = scan_local_stack.attribute_keys(rows)
    assert keys["span_attribute_keys"] == ["a", "b"]
    assert keys["resource_attribute_keys"] == ["project_name", "service"]
