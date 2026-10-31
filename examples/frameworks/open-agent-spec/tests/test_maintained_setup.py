"""Regression contracts for the maintained setup; synthetic model and loopback OTLP only."""

from pathlib import Path

import pytest

from conftest import by_name

EXAMPLE = Path(__file__).resolve().parent.parent
PAGE = EXAMPLE.parents[2] / "src/pages/docs/integrations/frameworks/open-agent-spec.mdx"


def test_page_uses_released_privacy_api_without_copied_exporter():
    text = PAGE.read_text(encoding="utf-8")
    assert "TraceConfig(hide_error_details=True)" in text
    assert '"fi-instrumentation-otel>=1.2.2"' in text
    assert '"traceai-langchain>=0.2.1"' in text
    assert "ErrorDetailFilter" not in text
    assert "futureagi_tracing" not in text
    assert not (EXAMPLE / "futureagi_tracing.py").exists()


@pytest.mark.parametrize("scenario,exception_type", [
    ("tool-error", "RuntimeError"),
    ("model-error", "openai.AuthenticationError"),
])
@pytest.mark.parametrize("hide_content", [False, True])
def test_error_details_hidden_independently_of_content(run_app, scenario, exception_type, hide_content):
    # Explicit application config wins even over an environment opt-out.
    run = run_app(
        scenario, "What is the weather in Lisbon right now?",
        FI_HIDE_INPUTS=str(hide_content).lower(),
        FI_HIDE_OUTPUTS=str(hide_content).lower(),
        FI_HIDE_ERROR_DETAILS="false",
    )
    assert run.returncode == 1, run.stderr[-2000:]
    assert run.recorder.requests
    raw = run.recorder.raw()
    for detail in (b"weather service unavailable", b"Invalid API key", b"Traceback (most recent call last)"):
        assert detail not in raw
    errors = [span for span in run.spans() if span["status"].get("code") == "STATUS_CODE_ERROR"]
    assert errors
    assert all(not span["status"].get("message") for span in errors)
    events = [event for span in errors for event in span["events"] if event["name"] == "exception"]
    assert events
    assert exception_type in {event["attributes"]["exception.type"] for event in events}
    assert all("exception.message" not in event["attributes"] for event in events)
    assert all("exception.stacktrace" not in event["attributes"] for event in events)
    if scenario == "tool-error":
        assert by_name(run.spans(), "get_weather")[0]["status"]["code"] == "STATUS_CODE_ERROR"
