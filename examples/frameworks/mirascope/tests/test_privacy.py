"""Content stays off the wire unless the app opts in; stack traces and local paths never leave.

The marker is in the prompt, in the tool argument and in the tool result, so a leak through any
of them is caught. The scan covers the decoded spans (attributes, events, status, resource,
scope) and the raw request bytes.
"""

from __future__ import annotations

import getpass
import socket

import pytest
from conftest import HERE, MARKER, MODEL_ID

from futureagi_tracing import METADATA_ATTRIBUTES

SCENARIOS = ["chat", "tool", "agent", "stream", "error", "trace"]
CONTENT_SCENARIOS = ["chat", "tool", "agent", "stream", "trace"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_default_exports_no_content(runs, scenario):
    run = runs(scenario)
    assert run.spans, run.stderr
    assert MARKER not in run.everything()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_default_exports_only_listed_attributes(runs, scenario):
    for span in runs(scenario).spans:
        extra = set(span["attributes"]) - METADATA_ATTRIBUTES
        assert not extra, (span["name"], extra)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_default_keeps_the_trace_useful(runs, scenario):
    names = {s["name"].split(" ")[0] for s in runs(scenario).spans}
    assert "chat" in names or scenario == "error"
    for span in runs(scenario).spans:
        if span["name"].startswith("chat "):
            assert span["attributes"]["gen_ai.request.model"]
            assert span["attributes"]["gen_ai.operation.name"] == "chat"


def test_default_drops_event_payloads(runs):
    plan = runs("trace").span("plan")
    assert [e["name"] for e in plan["events"]] == ["info"]
    assert plan["events"][0]["attributes"] == {}


def test_default_error_has_type_but_no_text(runs):
    span = runs("error").spans[0]
    assert span["status_code"] == 2
    assert span["status_message"] == "mirascope.llm.exceptions.NotFoundError"
    assert "does not exist" not in runs("error").everything()
    for event in span["events"]:
        assert set(event["attributes"]) == {"exception.type"}


@pytest.mark.parametrize("scenario", CONTENT_SCENARIOS)
def test_opt_in_exports_content(runs, scenario):
    run = runs(scenario, capture_content=True)
    assert run.spans, run.stderr
    assert MARKER in run.everything()
    chats = [s for s in run.spans if s["name"].startswith("chat ")]
    assert any(MARKER in str(c["attributes"].get("gen_ai.input.messages", "")) for c in chats)


def test_opt_in_exports_tool_payloads(runs):
    tool = runs("agent", capture_content=True).span("execute_tool get_weather")
    assert tool["attributes"]["city"] == MARKER
    assert MARKER in tool["attributes"]["result"]


def test_opt_in_exports_error_text(runs):
    span = runs("error", capture_content=True).spans[0]
    assert "does not exist" in span["status_message"]
    assert any("exception.message" in e["attributes"] for e in span["events"])


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("capture", [False, True])
def test_stack_traces_and_local_details_never_leave(runs, scenario, capture):
    run = runs(scenario, capture_content=capture)
    text = run.everything()
    assert "Traceback" not in text
    assert "exception.stacktrace" not in text
    assert "site-packages" not in text
    assert str(HERE) not in text
    assert "/Users/" not in text and "/home/" not in text
    assert socket.gethostname() not in text
    assert getpass.getuser() not in text


@pytest.mark.parametrize("capture", [False, True])
def test_resource_holds_only_project_and_sdk_attributes(runs, capture):
    resource = runs("chat", capture_content=capture).spans[0]["resource"]
    required = {
        "telemetry.sdk.language",
        "telemetry.sdk.name",
        "telemetry.sdk.version",
        "service.name",
        "project_name",
        "project_type",
    }
    # service.instance.id is a random UUID that newer SDKs add (1.45 does, 1.38 does not).
    assert required <= set(resource) <= required | {"service.instance.id"}
    assert resource["service.name"].startswith("unknown_service")


def test_the_default_does_not_depend_on_the_model_id(runs):
    # The model id is metadata and stays; it is what Future AGI shows as the model.
    assert any(MODEL_ID in s["name"] for s in runs("chat").spans)
