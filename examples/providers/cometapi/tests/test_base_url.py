"""G2 / R-07: the base URL. What the unmodified client dials, what a trailing slash does,
and what a base URL without /v1 looks like in the trace.

Nothing here reaches CometAPI. The refusing CONNECT probe answers 403 to the tunnel request
and opens nothing."""
from conftest import COMET_KEY, MODEL, comet_requests, llm_spans


def test_the_default_url_dials_api_cometapi_com_on_443_and_nothing_else(run_app, collector, probe):
    result = run_app("--scenario", "chat", use_stub=False, env={"HTTPS_PROXY": probe.url})
    assert result.returncode == 0
    assert {p["target"] for p in probe.seen} == {"api.cometapi.com:443"}
    assert {p["method"] for p in probe.seen} == {"CONNECT"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"  # the probe refused, so the call failed and is traced as failed
    assert span["_attrs"]["gen_ai.provider.name"] == "openai"
    # the span carries no CometAPI host or URL
    assert "cometapi" not in " ".join(str(v) for k, v in span["_attrs"].items() if k.startswith(("gen_ai.request", "gen_ai.provider", "http", "url")))


def test_a_trailing_slash_is_the_same_endpoint(run_app, collector, stub):
    """The PRD notes Langfuse writes https://api.cometapi.com/v1/ . The OpenAI client reaches the
    same path with or without the slash and the span is the same."""
    assert run_app("--scenario", "chat", base_url=stub.url + "/").returncode == 0
    assert {r["path"] for r in comet_requests(stub)} == {"/v1/chat/completions"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_OK" and span["_attrs"]["gen_ai.request.model"] == MODEL


def test_a_base_url_without_v1_is_a_failed_call_not_a_tracing_fault(run_app, collector, stub):
    """CometAPI's guide says a missing /v1 gives 404 and its error page says it may be a 301 or
    HTML. Neither was reproduced against CometAPI. The stand-in answers 404, and the call is
    traced as an ERROR span carrying the status, which is all this asserts."""
    result = run_app("--scenario", "chat", base_url=stub.root)
    assert result.returncode == 0
    assert "RESULT chat: NotFoundError" in result.stdout
    assert {r["path"] for r in comet_requests(stub)} == {"/chat/completions"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"
    assert "NotFoundError" in span["status"]["message"] and "404" in span["status"]["message"]
    assert COMET_KEY not in span["status"]["message"]
