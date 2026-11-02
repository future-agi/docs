"""The TypeScript recipe (@traceai/openai + @traceai/fi-core) behind both Helicone surfaces.

Needs `npm install` in typescript/ and Node 22.18+ (runs the .ts files directly). Skipped otherwise.
Tests assert the published @traceai/openai 0.1.15 behavior.
"""
import json
import os
import shutil
import subprocess

import pytest

from conftest import (
    FI_KEY,
    FI_SECRET,
    HELICONE_KEY,
    MARKER,
    PROJECT,
    PROVIDER_KEY,
    ROOT,
)

TS = ROOT / "typescript"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not (TS / "node_modules" / "@traceai" / "openai").exists(),
    reason="needs node and `npm install` in typescript/",
)


@pytest.fixture()
def run_ts(mock, capture):
    def _run(surface="gateway", scenarios="chat,tools,stream,error", env=None, expect_spans=4):
        e = dict(os.environ)
        for k in list(e):
            if k.startswith(("FI_HIDE", "HELICONE_", "OTEL_", "DEMO_")):
                del e[k]
        e.update(
            FI_BASE_URL=capture.url,
            FI_API_KEY=FI_KEY,
            FI_SECRET_KEY=FI_SECRET,
            FI_PROJECT_NAME=PROJECT,
            HELICONE_SURFACE=surface,
            HELICONE_BASE_URL=mock.gateway_base_url if surface == "gateway" else mock.proxy_base_url,
            HELICONE_API_KEY=HELICONE_KEY,
            OPENAI_API_KEY=PROVIDER_KEY,
            HELICONE_MODEL="openai/gpt-4o-mini",
            HELICONE_SESSION_ID="hel-session-ts-777",
            HELICONE_USER_ID="hel-user-ts-777",
            DEMO_MARKER=MARKER,
            DEMO_SCENARIOS=scenarios,
        )
        e.update(env or {})
        proc = subprocess.run(["node", "run-demo.ts"], cwd=TS, env=e, capture_output=True, text=True, timeout=120)
        capture.wait_for_spans(expect_spans, timeout=10)
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
        return proc, (json.loads(lines[-1]) if lines else None), capture

    return _run


@pytest.mark.parametrize("surface", ["gateway", "proxy"])
def test_model_usage_project(run_ts, surface):
    proc, summary, cap = run_ts(surface)
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert summary["scenarios"]["chat"] and summary["scenarios"]["tools"] and summary["scenarios"]["stream"]
    llm = [s for s in cap.spans if s.attributes.get("fi.span.kind") == "LLM"]
    nonstream = [s for s in llm if "gen_ai.usage.total_tokens" in s.attributes]
    assert sorted(s.attributes["gen_ai.usage.total_tokens"] for s in nonstream) == [48, 72, 72], [s.attributes for s in cap.spans]
    for s in nonstream:
        assert s.attributes["gen_ai.request.model"] == "gpt-4o-mini"  # the model the gateway reports back
        assert s.attributes["gen_ai.provider.name"] == "openai"  # every span, whatever the base URL
        assert s.status_code == 1
    for s in cap.spans:
        assert s.resource["project_name"] == PROJECT
        assert s.resource["project_type"] == "observe"
    for req in cap.requests:
        assert req["path"] == "/tracer/v1/traces"
        assert req["headers"]["x-api-key"] == FI_KEY
        assert req["headers"]["x-secret-key"] == FI_SECRET
        assert "content-encoding" not in req["headers"]


@pytest.mark.parametrize("surface", ["gateway", "proxy"])
def test_helicone_headers_and_keys_stay_out_of_spans(run_ts, mock, surface):
    proc, _, cap = run_ts(surface)
    sent = [r for r in mock.requests if r["path"].startswith("/" + ("gw" if surface == "gateway" else "proxy"))]
    assert sent[0]["headers"]["helicone-session-id"] == "hel-session-ts-777"
    if surface == "proxy":
        assert sent[0]["headers"]["helicone-auth"] == f"Bearer {HELICONE_KEY}"
    blob = json.dumps([s.to_dict() for s in cap.spans]) + json.dumps([r["headers"] for r in cap.requests])
    for needle in ("hel-session-ts-777", "hel-user-ts-777", HELICONE_KEY, PROVIDER_KEY):
        assert needle not in blob
    for s in cap.spans:
        assert not any("helicone" in k.lower() for k in s.attributes)
        assert "session.id" not in s.attributes and "user.id" not in s.attributes


def test_streamed_call(run_ts):
    """A streamed call carries its output but omits usage when the response has none."""
    _, _, cap = run_ts("gateway", scenarios="stream", expect_spans=1)
    [span] = cap.spans
    assert span.attributes["output.value"].startswith("It is 21C")
    assert span.attributes["gen_ai.request.model"] == "openai/gpt-4o-mini"
    assert "gen_ai.usage.total_tokens" not in span.attributes
    assert span.status_code == 0


def test_failed_call_is_traced(run_ts):
    """The published instrumentor exports an ERROR span for a rejected SDK call."""
    proc, summary, cap = run_ts("gateway", scenarios="error", expect_spans=1)
    assert summary["scenarios"]["error"] == "InternalServerError"  # the app saw the failure
    assert len(cap.spans) == 1 and cap.spans[0].status_code == 2, [s.to_dict() for s in cap.spans]


def test_hide_settings_mask_content(run_ts):
    """The published instrumentor masks ordinary chat prompts and responses."""
    _, _, cap = run_ts("gateway", scenarios="chat", env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"}, expect_spans=1)
    assert MARKER not in json.dumps([s.to_dict() for s in cap.spans])


def test_tool_schema_privacy_claim_matches_export(run_ts):
    """If the installed package exports tool schemas, the guide must warn about it."""
    from conftest import TOOL_MARKER

    _, _, cap = run_ts(
        "gateway", scenarios="tools",
        env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true",
             "FI_HIDE_LLM_INVOCATION_PARAMETERS": "true", "DEMO_TOOL_DESCRIPTION": TOOL_MARKER},
        expect_spans=2,
    )
    exposed = [s for s in cap.spans if TOOL_MARKER in json.dumps(s.attributes)]
    if exposed:
        guide = (ROOT.parents[2] / "src/pages/docs/integrations/gateways/helicone.mdx").read_text()
        assert "The TypeScript SDK does not mask tool definitions or `gen_ai.request.parameters`" in guide
    assert len(cap.spans) == 2
