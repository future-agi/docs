"""Conformance of the existing traceai-openai instrumentor behind Helicone's two surfaces.

Runs python/run_demo.py (the code the docs page shows) against a local stand-in that speaks
the OpenAI wire format, with `register()` pointed at a local OTLP receiver. Nothing leaves
the machine and no Helicone or provider key is used.

The assertions hold for traceai-openai 0.1.10 (the latest release when this was written) and for
the unreleased fix in future-agi/traceAI#249, which records the requested model on streamed and
failed calls. Where the two differ the test accepts both.
"""
import getpass
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    ERROR_MARKER,
    FI_KEY,
    FI_SECRET,
    HELICONE_KEY,
    MARKER,
    PROJECT,
    PROVIDER_KEY,
    TOOL_MARKER,
    ROOT,
)

SURFACES = ["gateway", "proxy"]


@pytest.mark.parametrize("surface", SURFACES)
def test_agent_trace_model_usage_project(run_python, surface):
    """AC-01 / AC-02: both surfaces produce LLM spans with model and usage, in the register() project."""
    run = run_python(surface, ["--scenario", "agent"], expect_spans=4)
    assert run.proc.returncode == 0, run.proc.stderr[-1500:]
    assert run.summary["scenarios"] == {"agent": True}

    # hierarchy: agent -> (llm, tool, llm)
    agent = run.by_kind("AGENT")
    assert len(agent) == 1 and agent[0].parent_span_id == ""
    children = [s for s in run.spans if s.parent_span_id == agent[0].span_id]
    assert sorted(s.attributes["gen_ai.span.kind"] for s in children) == ["LLM", "LLM", "TOOL"]

    llm = sorted(run.by_kind("LLM"), key=lambda s: s.attributes["gen_ai.usage.total_tokens"])
    assert [s.attributes["gen_ai.usage.total_tokens"] for s in llm] == [48, 72]
    assert llm[0].attributes["gen_ai.usage.input_tokens"] == 31
    assert llm[0].attributes["gen_ai.usage.output_tokens"] == 17
    for s in llm:
        # the model the gateway reports back: no "openai/" prefix, even though the request used one
        assert s.attributes["gen_ai.request.model"] == "gpt-4o-mini"
        # the requested name stays in the invocation parameters
        assert json.loads(s.attributes["gen_ai.request.parameters"])["model"] == "openai/gpt-4o-mini"
        # the instrumentor labels every span "openai", whatever the base URL host is
        assert s.attributes["gen_ai.provider.name"] == "openai"
        assert s.resource["project_name"] == PROJECT
        assert s.resource["project_type"] == "observe"
        assert s.status_code == 1


@pytest.mark.parametrize("surface", SURFACES)
def test_collector_wire_format(run_python, surface):
    """register() posts uncompressed OTLP to /tracer/v1/traces with the Future AGI key headers."""
    run = run_python(surface, ["--scenario", "agent"], expect_spans=4)
    assert run.capture.requests, "no OTLP request reached the receiver"
    for req in run.capture.requests:
        assert req["path"] == "/tracer/v1/traces"
        assert req["headers"]["x-api-key"] == FI_KEY
        assert req["headers"]["x-secret-key"] == FI_SECRET
        assert "content-encoding" not in req["headers"]


def test_helicone_auth_shapes_are_not_interchangeable(run_python, mock):
    """AC-01: the AI Gateway takes the Helicone key as api_key; the classic proxy needs Helicone-Auth."""
    run_python("gateway", ["--scenario", "agent", "--no-helicone-headers"], expect_spans=4)
    gw = [r for r in mock.requests if r["path"].startswith("/gw")]
    assert gw and all(r["headers"]["authorization"] == f"Bearer {HELICONE_KEY}" for r in gw)
    assert all("helicone-auth" not in r["headers"] for r in gw)

    mock.requests.clear()
    run_python("proxy", ["--scenario", "agent", "--no-helicone-headers"], expect_spans=4)
    px = [r for r in mock.requests if r["path"].startswith("/proxy")]
    assert px and all(r["headers"]["authorization"] == f"Bearer {PROVIDER_KEY}" for r in px)
    assert all(r["headers"]["helicone-auth"] == f"Bearer {HELICONE_KEY}" for r in px)


def test_mixing_the_two_surfaces_fails(mock):
    """Using one surface's auth on the other surface's URL is a 401, not a silent success."""
    sys.path.insert(0, str(ROOT / "python"))
    from openai import AuthenticationError, OpenAI

    from helicone_tracing import GATEWAY, PROXY, make_client

    msgs = [{"role": "user", "content": "hi"}]
    gw_client_on_proxy_url = make_client(GATEWAY, helicone_key=HELICONE_KEY, base_url=mock.proxy_base_url, max_retries=0)
    with pytest.raises(AuthenticationError):
        gw_client_on_proxy_url.chat.completions.create(model="m", messages=msgs)
    # proxy-style client (OpenAI key + Helicone-Auth) on the gateway URL: gateway wants the Helicone key as api_key
    px_client_on_gw_url = make_client(PROXY, helicone_key=HELICONE_KEY, provider_key=PROVIDER_KEY, base_url=mock.gateway_base_url, max_retries=0)
    with pytest.raises(AuthenticationError):
        px_client_on_gw_url.chat.completions.create(model="m", messages=msgs)
    # and the right shape works on each
    assert make_client(GATEWAY, helicone_key=HELICONE_KEY, base_url=mock.gateway_base_url, max_retries=0).chat.completions.create(model="m", messages=msgs)
    assert make_client(PROXY, helicone_key=HELICONE_KEY, provider_key=PROVIDER_KEY, base_url=mock.proxy_base_url, max_retries=0).chat.completions.create(model="m", messages=msgs)
    assert OpenAI  # imported for the error classes above


@pytest.mark.parametrize("surface", SURFACES)
def test_helicone_credentials_never_reach_the_collector(run_python, surface):
    run = run_python(surface, ["--scenario", "agent"], expect_spans=4)
    blob = run.dump() + json.dumps([r["headers"] for r in run.capture.requests])
    for secret in (HELICONE_KEY, PROVIDER_KEY):
        assert secret not in blob
    assert "helicone-auth" not in blob.lower()
    assert "authorization" not in blob.lower()


@pytest.mark.parametrize("surface", SURFACES)
def test_helicone_headers_are_not_mapped_to_session_or_user(run_python, mock, surface):
    """AC-05: Helicone-Session-Id / -User-Id / -Property-* are sent to Helicone and are not copied onto spans."""
    run = run_python(
        surface,
        ["--scenario", "agent", "--no-fi-session", "--helicone-session-id", "hel-session-777", "--helicone-user-id", "hel-user-777"],
        expect_spans=4,
    )
    sent = mock.requests[0]["headers"]
    assert sent["helicone-session-id"] == "hel-session-777"
    assert sent["helicone-user-id"] == "hel-user-777"
    assert sent["helicone-property-environment"] == "e2e"
    blob = run.dump()
    assert "hel-session-777" not in blob and "hel-user-777" not in blob
    for s in run.spans:
        assert "session.id" not in s.attributes and "user.id" not in s.attributes
        assert not any("helicone" in k.lower() for k in s.attributes), "a Helicone header became a span attribute"
    # response headers (the stand-in sends helicone-id) are not recorded either
    assert "mock-helicone-request-id" not in blob


def test_future_agi_session_and_user_come_from_the_traceai_api(run_python):
    """The documented way to get a session / user in Future AGI is using_session / using_user."""
    run = run_python(
        "gateway",
        ["--scenario", "agent", "--session-id", "fi-session-123", "--user-id", "fi-user-123",
         "--helicone-session-id", "hel-session-777", "--helicone-user-id", "hel-user-777"],
        expect_spans=4,
    )
    for s in run.spans:
        assert s.attributes["session.id"] == "fi-session-123"
        assert s.attributes["user.id"] == "fi-user-123"
    assert "hel-session-777" not in run.dump()


@pytest.mark.parametrize("surface", SURFACES)
def test_default_exports_prompts_and_responses(run_python, surface):
    """Default: the instrumentor exports content (this is the opt-out side of the privacy switch)."""
    run = run_python(surface, ["--scenario", "agent"], expect_spans=4)
    blob = run.dump()
    assert MARKER in blob
    assert "jane.doe@example.com" in blob  # the email in the prompt is content, exported by default
    llm = run.by_kind("LLM")
    assert any(MARKER in s.attributes.get("output.value", "") for s in llm)
    # the tool span carries the tool arguments and the tool result (the marker is passed as case_ref)
    [tool] = run.by_kind("TOOL")
    assert MARKER in tool.attributes["input.value"] and MARKER in tool.attributes["output.value"]


@pytest.mark.parametrize("surface", SURFACES)
def test_hide_settings_remove_prompt_response_and_tool_io(run_python, surface):
    """AC-03: FI_HIDE_INPUTS / FI_HIDE_OUTPUTS keep the unique marker out of every exported field."""
    run = run_python(
        surface,
        ["--scenario", "all"],
        env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"},
        expect_spans=8,
    )
    assert run.proc.returncode == 0, run.proc.stderr[-1500:]
    assert run.spans, "hiding content must not drop the spans"
    blob = run.dump()
    assert MARKER not in blob, "prompt / response / tool args / tool result leaked through the hide settings"
    assert "jane.doe@example.com" not in blob
    assert "__REDACTED__" in blob
    # tool arguments and tool result are content too
    tools = run.by_kind("TOOL")
    assert tools and all(MARKER not in json.dumps(t.to_dict()) for t in tools)
    assert tools[0].attributes["input.value"] == "__REDACTED__" and tools[0].attributes["output.value"] == "__REDACTED__"
    # usage and model are not content: they are still there
    llm = [s for s in run.by_kind("LLM") if s.status_code == 1]
    assert llm and all("gen_ai.usage.total_tokens" in s.attributes or "gen_ai.request.model" not in s.attributes for s in llm)
    assert any(s.attributes.get("gen_ai.usage.total_tokens") for s in llm)


def test_tool_definitions_are_not_masked_by_the_hide_settings(run_python):
    """Documented limitation (traceai-openai 0.1.10): tool names, descriptions and schemas are exported even
    with FI_HIDE_INPUTS=true. If this starts failing the limitation was fixed: update the docs page."""
    run = run_python(
        "gateway", ["--scenario", "agent"], env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"}, expect_spans=4
    )
    assert TOOL_MARKER in run.dump()


@pytest.mark.parametrize("surface", SURFACES)
def test_failed_call_is_an_error_span_with_raw_error_text(run_python, surface):
    """R-08: a failed call is an ERROR span. Hide settings do not remove the error text or stack trace."""
    run = run_python(
        surface,
        ["--scenario", "error"],
        env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"},
        expect_spans=1,
    )
    assert run.summary["scenarios"]["error"] == "InternalServerError"
    [span] = run.spans
    assert span.status_code == 2
    assert ERROR_MARKER in span.status_message
    exc = [e for e in span.events if e["name"] == "exception"]
    assert exc and ERROR_MARKER in exc[0]["attributes"]["exception.message"]
    assert "Traceback" in exc[0]["attributes"]["exception.stacktrace"]
    assert MARKER not in run.dump()  # the prompt itself is still hidden


@pytest.mark.parametrize("surface", SURFACES)
def test_auth_error_is_an_error_span(run_python, surface):
    run = run_python(surface, ["--scenario", "auth-error"], expect_spans=1)
    assert run.summary["scenarios"]["auth-error"] == "AuthenticationError"
    [span] = run.spans
    assert span.status_code == 2
    assert any(e["name"] == "exception" and e["attributes"]["exception.type"].endswith("AuthenticationError") for e in span.events)
    assert span.resource["project_name"] == PROJECT


def test_scrub_exporter_removes_error_details(run_python):
    """The tested mitigation: RedactErrorDetailsExporter keeps ERROR + the exception class, drops text and stack."""
    run = run_python(
        "gateway",
        ["--scenario", "all", "--scrub-errors"],
        env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"},
        expect_spans=8,
    )
    assert run.proc.returncode == 0, run.proc.stderr[-1500:]
    errors = [s for s in run.spans if s.status_code == 2]
    assert errors, "the failed call must still be an ERROR span"
    for s in errors:
        assert s.status_message == ""
        ev = [e for e in s.events if e["name"] == "exception"]
        assert ev and ev[0]["attributes"]["exception.type"].endswith(("InternalServerError", "AuthenticationError"))
        assert "exception.message" not in ev[0]["attributes"]
        assert "exception.stacktrace" not in ev[0]["attributes"]
    blob = run.dump()
    # content-off proof: marker, upstream error text, stack trace, local paths, user name, host name
    for needle in (
        MARKER,
        ERROR_MARKER,
        "Traceback",
        "site-packages",
        str(Path.home()),
        os.getcwd(),
        getpass.getuser(),
        socket.gethostname(),
        "@example.com",
    ):
        assert needle not in blob, f"{needle!r} was exported"


@pytest.mark.parametrize("include_usage", [True, False])
def test_streaming(run_python, include_usage):
    """R-07: streamed text is captured; usage only when the stream carries it; no usage is not zero."""
    args = ["--scenario", "stream"] + ([] if include_usage else ["--no-stream-usage"])
    run = run_python("gateway", args, expect_spans=2)
    llm = run.by_kind("LLM")
    assert len(llm) == 1
    attrs = llm[0].attributes
    if include_usage:
        assert attrs["gen_ai.usage.total_tokens"] == 72
        assert attrs["gen_ai.usage.input_tokens"] == 63
    else:
        assert "gen_ai.usage.total_tokens" not in attrs
    # 0.1.10 omits the model on streamed calls; the unreleased #249 records the requested one
    assert attrs.get("gen_ai.request.model") in (None, "openai/gpt-4o-mini", "gpt-4o-mini")
    assert attrs["output.value"].startswith("It is 21C") and MARKER in attrs["output.value"]


def test_hosted_base_urls_build_the_documented_requests():
    """The base URLs the page publishes, run through the SDK and instrumentor on an in-process transport.
    STANDIN: nothing here contacts Helicone; it shows the path and headers the client builds."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "hosted_shape_probe.py")],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["gateway"]["request"]["url"] == "https://ai-gateway.helicone.ai/chat/completions"
    assert out["gateway"]["request"]["helicone_auth"] == "absent"
    assert out["gateway"]["request"]["authorization_carries"] == "helicone-key"
    assert out["proxy"]["request"]["url"] == "https://oai.helicone.ai/v1/chat/completions"
    assert out["proxy"]["request"]["helicone_auth"] == "present"
    assert out["proxy"]["request"]["authorization_carries"] == "openai-key"
    for surface in ("gateway", "proxy"):
        assert out[surface]["provider_attr"] == "openai"  # neither Helicone host is in the instrumentor's table
        assert out[surface]["model_attr"] == "gpt-4o-mini"
