"""The base URL, which is what this ticket is about.

Novita's own pages show two base URLs for the OpenAI client: https://api.novita.ai/openai/v1
(quickstart, Hermes guide, the curl examples) and https://api.novita.ai/openai (API overview and
several SDK guides). Langfuse's Novita page shows a third, https://api.novita.ai/v3/openai.

These tests show what the unmodified client dials, what request path each form produces, and what
each form looks like in the trace. Nothing here reaches Novita. The refusing CONNECT probe answers
403 to the tunnel request and opens nothing, and the local stand-in decides which paths it routes."""

import pytest
from conftest import MODEL, NOVITA_KEY, novita_requests, llm_spans, start_stub

def test_the_default_url_dials_api_novita_ai_on_443_and_nothing_else(run_app, collector, probe):
    result = run_app("--scenario", "chat", use_stub=False, env={"HTTPS_PROXY": probe.url})
    assert result.returncode == 0
    assert {p["target"] for p in probe.seen} == {"api.novita.ai:443"}
    assert {p["method"] for p in probe.seen} == {"CONNECT"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"  # the probe refused, so the call failed and is traced as failed
    assert span["_attrs"]["gen_ai.provider.name"] == "openai"
    # the span carries no Novita host or URL
    assert "novita" not in " ".join(str(v) for k, v in span["_attrs"].items() if k.startswith(("gen_ai.request", "gen_ai.provider", "http", "url", "server")))


def test_the_unversioned_openai_url_dials_the_same_host(run_app, collector, probe):
    result = run_app(
        "--scenario", "chat", use_stub=False, env={"HTTPS_PROXY": probe.url, "NOVITA_BASE_URL": "https://api.novita.ai/openai"}
    )
    assert result.returncode == 0
    assert {p["target"] for p in probe.seen} == {"api.novita.ai:443"}


def test_each_form_makes_the_client_request_a_different_path(run_app, stub):
    """The OpenAI client appends /chat/completions to whatever base URL it is given."""
    assert run_app("--scenario", "chat", base_url=stub.url).returncode == 0
    assert run_app("--scenario", "chat", base_url=stub.bare_url).returncode == 0
    assert [r["path"] for r in novita_requests(stub)] == ["/openai/v1/chat/completions", "/openai/chat/completions"]


def test_a_trailing_slash_is_the_same_endpoint(run_app, collector, stub):
    assert run_app("--scenario", "chat", base_url=stub.url + "/").returncode == 0
    assert {r["path"] for r in novita_requests(stub)} == {"/openai/v1/chat/completions"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_OK" and span["_attrs"]["gen_ai.request.model"] == MODEL


def test_the_span_is_the_same_whichever_of_novitas_two_urls_the_client_uses(run_app, collector, stub):
    """traceai-openai reads only the host of base_url, never the path. So the path Novita routes is
    Novita's business and the trace does not change. Observed on the stand-in, which serves both."""
    for url in (stub.url, stub.bare_url):
        result = run_app("--scenario", "chat", "--prompt", "same prompt", "--session-id", "same-session", base_url=url)
        assert result.returncode == 0
    first, second = llm_spans(collector)
    assert first["status"]["code"] == second["status"]["code"] == "STATUS_CODE_OK"
    assert first["name"] == second["name"]
    assert first["_attrs"] == second["_attrs"]  # every attribute, session id included, because both runs share one


@pytest.mark.parametrize(
    "served, wrong_form",
    [(("/openai/v1/chat/completions",), "bare_url"), (("/openai/chat/completions",), "url")],
)
def test_a_form_the_server_does_not_route_is_a_failed_call_not_a_tracing_fault(run_app, collector, served, wrong_form):
    """If the live service routed only one of Novita's two forms, the other would fail. Simulated
    here by a stand-in that serves only one path: the call is traced as an ERROR span carrying the
    HTTP status, and the key never appears in it."""
    only = start_stub(paths=served)
    try:
        result = run_app("--scenario", "chat", base_url=getattr(only, wrong_form))
    finally:
        only.shutdown()
    assert result.returncode == 0
    assert "RESULT chat: NotFoundError" in result.stdout
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"
    assert "NotFoundError" in span["status"]["message"] and "404" in span["status"]["message"]
    assert NOVITA_KEY not in span["status"]["message"]


def test_langfuses_v3_openai_path_is_not_routed_by_the_stand_in(run_app, collector, stub):
    """https://api.novita.ai/v3/openai is on Langfuse's Novita page and in no Novita page read on
    2026-10-15. The stand-in does not route it, so the call fails and is traced as an error. This is
    the stand-in's choice, not a measurement of Novita."""
    result = run_app("--scenario", "chat", base_url=stub.root + "/v3/openai")
    assert result.returncode == 0
    assert "RESULT chat: NotFoundError" in result.stdout
    assert {r["path"] for r in novita_requests(stub)} == {"/v3/openai/chat/completions"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"


def test_the_span_records_neither_the_host_nor_the_path(run_app, collector, stub):
    assert run_app("--scenario", "chat").returncode == 0
    (span,) = llm_spans(collector)
    blob = " ".join(str(v) for v in span["_attrs"].values())
    assert stub.root not in blob and "/openai/v1" not in blob and "127.0.0.1" not in blob
