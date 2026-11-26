"""Privacy on the wire.

* content is captured by default; explicit error privacy hides messages and stack traces;
* FI_HIDE_INPUTS=true + FI_HIDE_OUTPUTS=true: the marker (in the question, the tool
  arguments, the tool result, the tool error and the answer) never leaves the process,
  and neither does the system prompt or the error text.

The marker is scanned in the raw request bodies, so resource attributes, span events and
every attribute are covered.
"""

from __future__ import annotations

import getpass
import os
import socket

import pytest

from conftest import SYSTEM_PROMPT_PHRASE, by_name, kind

HIDE = {"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"}


def question(marker: str) -> str:
    return f"What is the weather in {marker}? Repeat the city name {marker} in your answer."


def local_identity() -> list[bytes]:
    needles = [os.getcwd(), os.path.expanduser("~"), "Traceback (most recent call last)"]
    user = getpass.getuser()
    if len(user) >= 4:
        needles.append(user)
    host = socket.gethostname()
    if len(host) >= 4:
        needles.append(host)
    return [n.encode() for n in needles]


@pytest.mark.parametrize("scenario", ["chat", "tool-error"])
def test_default_captures_content_but_no_stack_trace(run_app, marker, scenario):
    run = run_app(scenario, question(marker))
    raw = run.recorder.raw()
    assert marker.encode() in raw, "traceAI's default captures content"
    assert SYSTEM_PROMPT_PHRASE.encode() in raw
    for needle in local_identity():
        assert needle not in raw, f"{needle!r} exported"
    for span in run.spans():
        for event in span["events"]:
            assert "exception.stacktrace" not in event["attributes"]
        assert "exception.stacktrace" not in span["attributes"]


@pytest.mark.parametrize("scenario", ["chat", "async", "tool-error", "model-error"])
def test_hidden_content_never_leaves_the_process(run_app, marker, scenario):
    run = run_app(scenario, question(marker), **HIDE)
    assert run.recorder.requests, "spans are still exported with content hidden"
    raw = run.recorder.raw()
    assert marker.encode() not in raw
    assert SYSTEM_PROMPT_PHRASE.encode() not in raw
    assert b"weather service unavailable" not in raw
    assert b"Invalid API key" not in raw
    for needle in local_identity():
        assert needle not in raw, f"{needle!r} exported"
    for key in ("FI_API_KEY", "FI_SECRET_KEY", "MODEL_API_KEY", "MODEL_BAD_API_KEY"):
        assert run.env[key].encode() not in raw


def test_hidden_keeps_the_metadata(run_app, marker):
    run = run_app("tool-error", question(marker), **HIDE)
    spans = run.spans()
    tool = by_name(spans, "get_weather")[0]
    assert tool["status"] == {"code": "STATUS_CODE_ERROR"}
    assert any(event["attributes"].get("exception.type") == "RuntimeError" for event in tool["events"])
    llm = [s for s in spans if kind(s) == "LLM"][0]
    assert llm["attributes"]["gen_ai.request.model"] == "fake-model"
    assert llm["attributes"]["gen_ai.usage.input_tokens"] == 17
    assert [s["name"] for s in spans if not s["parentSpanId"]] == ["weather_assistant"]
