"""app.py, configured as the page says, exports the expected spans to a recording collector."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid

import pytest

pytest.importorskip("traceai_typesafe")
pytest.importorskip("opentelemetry.proto")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HIDE = ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_INPUT_TEXT", "FI_HIDE_OUTPUT_TEXT", "FI_PII_REDACTION")


def run(scenario, stub, collector, **env):
    environment = {k: v for k, v in os.environ.items() if k not in _HIDE and not k.startswith("TYPESAFE_")}
    environment.update(
        FI_API_KEY="test-fi-key",
        FI_SECRET_KEY="test-fi-secret",
        FI_BASE_URL=collector.url,
        FI_PROJECT_NAME="typesafe-test",
        TYPESAFE_BASE_URL=stub,
        TYPESAFE_API_KEY="standin-key",
        **env,
    )
    done = subprocess.run(
        [sys.executable, "app.py", "--scenario", scenario],
        cwd=HERE, env=environment, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return done.stdout


def test_ok_scenario_spans(stub, collector):
    out = run("ok", stub, collector)
    assert "RESULT scenario=ok outcome=ok" in out
    spans = collector.spans()
    by_name = {}
    for span in spans:
        by_name.setdefault(span["name"], []).append(span)
    (root,) = by_name["triage_ticket"]
    decisions = by_name["typesafe.system_one"]
    assert len(decisions) == 2  # sync + async; models.list makes none
    assert len(spans) == 3
    for span in decisions:
        a = span["attributes"]
        assert span["parent"] == root["span_id"]
        assert a["gen_ai.span.kind"] == "EVALUATOR"
        assert a["gen_ai.provider.name"] == "typesafe"
        assert a["gen_ai.request.model"] == "jev-latest"
        assert a["typesafe.response.model"] == "jev-1.13.0"
        assert a["session.id"] == root["attributes"]["session.id"]
        assert span["resource"]["project_name"] == "typesafe-test"
    sync = next(s for s in decisions if s["attributes"]["typesafe.question_count"] == 3)
    assert sync["attributes"]["typesafe.question.tone.type"] == "choice"
    assert "typesafe.question.billing.confidence" not in sync["attributes"]
    headers = {k.lower(): v for k, v in collector.requests[0]["headers"].items()}
    assert headers["x-api-key"] == "test-fi-key" and headers["x-secret-key"] == "test-fi-secret"
    assert "gzip" not in headers.get("content-encoding", "")
    assert collector.requests[0]["path"].endswith("/v1/traces")


@pytest.mark.parametrize("hidden", [True, False])
def test_marker_only_with_content_capture_on(stub, collector, hidden):
    marker = "TSTEST-" + uuid.uuid4().hex
    env = {"RUN_MARKER": marker}
    if hidden:
        env.update(FI_HIDE_INPUTS="true", FI_HIDE_OUTPUTS="true")
    for scenario in ("ok", "fail-422", "fail-asset"):
        run(scenario, stub, collector, **env)
    raw = collector.raw()
    assert (marker.encode() in raw) is (not hidden)
    # Never, in either mode: the stand-in key, the Future AGI keys, the temp path of the missing image.
    for secret in ("standin-key", "test-fi-key", "test-fi-secret", tempfile.gettempdir()):
        assert secret.encode() not in raw, secret


def test_failure_scenarios_are_error_spans(stub, collector):
    for scenario in ("fail-422", "fail-auth", "fail-asset"):
        run(scenario, stub, collector)
    errors = {
        s["attributes"]["error.type"]: s
        for s in collector.spans()
        if s["name"] == "typesafe.system_one"
    }
    assert set(errors) == {"TypeSafeUnprocessableEntityError", "TypeSafeAuthenticationError", "TypeSafeError"}
    for span in errors.values():
        assert span["status"] == 2  # STATUS_CODE_ERROR
        assert all("exception.stacktrace" not in attrs for _, attrs in span["events"])
    assert errors["TypeSafeAuthenticationError"]["attributes"]["http.response.status_code"] == 401
    assert errors["TypeSafeUnprocessableEntityError"]["attributes"]["http.response.status_code"] == 422
    assert errors["TypeSafeError"]["status_message"] == "TypeSafeError"
