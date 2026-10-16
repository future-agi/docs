"""The real traceAI-openai client, run as a separate process with NO Future AGI keys, exports through the APIM stand-in."""
import json
import uuid

from conftest import GW_FI_KEY, GW_FI_SECRET, SUB_KEY


def marker():
    return f"MARKER-{uuid.uuid4().hex[:12]}"


def test_traces_reach_the_collector_with_the_gateways_keys_not_the_apps(run_app, backend):
    r = run_app("--prompt", "hello")
    assert r.returncode == 0, r.stderr[-1500:]
    assert backend.requests
    for req in backend.requests:
        assert req["path"] == "/tracer/v1/traces"
        assert req["headers"]["x-api-key"] == GW_FI_KEY and req["headers"]["x-secret-key"] == GW_FI_SECRET
        assert "ocp-apim-subscription-key" not in req["headers"]
        assert req["headers"].get("content-encoding") is None  # APIM would pass a gzip body through, and the collector refuses it
    spans = backend.spans()
    assert {s["_resource"]["project_name"] for s in spans} == {"proj-test"}
    kinds = {s["_attrs"].get("gen_ai.span.kind") for s in spans}
    assert {"LLM", "AGENT", "TOOL"} <= kinds
    assert GW_FI_KEY.encode() not in b"".join(json.dumps(s).encode() for s in spans)


def test_the_app_refuses_to_run_with_future_agi_keys_set(run_app):
    r = run_app("--scenario", "chat", env={"FI_API_KEY": "x", "FI_SECRET_KEY": "y"})
    assert r.returncode == 2 and "only the APIM policy holds them" in r.stderr


def test_a_missing_subscription_key_is_a_missing_trace_not_a_failed_call(run_app, backend):
    r = run_app("--scenario", "chat", env={"APIM_SUBSCRIPTION_KEY": ""})
    assert r.returncode == 0 and "RESULT chat: echo:" in r.stdout
    assert backend.requests == []


def test_failure_case_is_an_error_span(run_app, backend):
    r = run_app("--scenario", "error")
    assert "RESULT error: HTTP 401" in r.stdout
    failed = [s for s in backend.spans() if s.get("status", {}).get("code") == "STATUS_CODE_ERROR"]
    assert failed


def test_content_is_captured_by_default_and_hidden_with_the_traceai_flags(run_app, backend):
    m = marker()
    assert run_app("--prompt", f"find {m}", "--system", f"note {m}").returncode == 0
    assert m.encode() in backend.raw() or any(m in json.dumps(s) for s in backend.spans())
    backend.requests.clear()
    m2 = marker()
    r = run_app("--prompt", f"find {m2}", "--system", f"note {m2}", env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"})
    assert r.returncode == 0 and backend.requests
    assert m2.encode() not in backend.raw()
    assert not any(m2 in json.dumps(s) for s in backend.spans())
