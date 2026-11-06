"""Offline tests for tools/check_trace.py (no Docker needed): python -m pytest tools/tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_trace  # noqa: E402


def span(i, parent, name, kind="unknown", status="OK", message="", model="", tokens=(0, 0)):
    return {"trace_id": "t", "id": i, "parent_span_id": parent, "name": name, "observation_type": kind,
            "status": status, "status_message": message, "model": model,
            "prompt_tokens": tokens[0], "completion_tokens": tokens[1]}


def good_trace(tool_status="OK", tool_message=""):
    return [
        span("a", "", "agent WeatherAgent", "agent"),
        span("b", "a", "action report"),
        span("c", "b", "llm gpt-6-luna"),
        span("d", "c", "tool-loop"),
        span("e", "d", "chat gpt-6-luna", "llm", model="gpt-6-luna", tokens=(560, 58)),
        span("f", "d", "execute_tool currentWeather", "tool", status=tool_status, message=tool_message),
        span("g", "d", "llm.invocation gpt-6-luna", tokens=(560, 58)),
        span("h", "b", "tool-loop-completed"),
    ]


def test_good_trace_passes():
    assert check_trace.check_trace(good_trace(), content_off=True) == ([], False)


def test_tool_error_is_counted_and_empty_message_passes_with_content_off():
    assert check_trace.check_trace(good_trace("ERROR"), content_off=True) == ([], True)


def test_error_text_fails_with_content_off_only():
    fails, errored = check_trace.check_trace(good_trace("ERROR", "station is offline"), content_off=True)
    assert errored and fails == ["errors: tool status message is not empty with content off"]
    assert check_trace.check_trace(good_trace("ERROR", "station is offline"), content_off=False) == ([], True)


def test_broken_hierarchy_and_missing_tokens_fail():
    spans = good_trace()
    spans[4] = span("e", "b", "chat gpt-6-luna", "llm", model="gpt-6-luna")
    fails, _ = check_trace.check_trace(spans, content_off=True)
    assert "hierarchy: chat gpt-6-luna under 'action report'" in fails
    assert "llm: chat gpt-6-luna has no token counts" in fails


def test_wrong_root_fails():
    spans = good_trace()[1:]
    fails, _ = check_trace.check_trace(spans, content_off=True)
    assert fails and fails[0].startswith("root:")
