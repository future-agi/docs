"""Where the unmodified recipe client dials when it uses the documented Z.ai URL.

No request leaves the machine: HTTPS_PROXY points at a probe that records the
`CONNECT host:port` the client asks for and answers 403. That is the strongest statement
possible about api.z.ai without a Z.ai account: the documented base URL makes the OpenAI
client dial exactly that host, on 443."""
from conftest import kind, llm_spans


def test_the_documented_url_dials_exactly_api_z_ai_443(run_app, collector, probe):
    result = run_app("--scenario", "chat", env={"HTTPS_PROXY": probe.url}, use_stub=False)
    assert result.returncode == 0, result.stderr[-1500:]
    assert "RESULT chat: APIConnectionError" in result.stdout
    assert "base_url=https://api.z.ai/api/paas/v4/" in result.stdout
    assert probe.seen, "the client never tried to connect"
    assert {p["target"] for p in probe.seen} == {"api.z.ai:443"}
    assert {p["method"] for p in probe.seen} == {"CONNECT"}


def test_the_connection_failure_is_an_error_span_labelled_openai(run_app, collector, probe):
    assert run_app("--scenario", "chat", env={"HTTPS_PROXY": probe.url}, use_stub=False).returncode == 0
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"
    assert "APIConnectionError" in span["status"]["message"]
    assert span["_attrs"]["gen_ai.provider.name"] == "openai"
    assert collector.spans()[0]["_resource"]["project_name"] == "z-ai-test"
    assert {kind(s) for s in collector.spans()} == {"AGENT", "LLM"}


def test_the_exported_bytes_do_not_name_the_zai_host(run_app, collector, probe):
    assert run_app("--scenario", "chat", env={"HTTPS_PROXY": probe.url}, use_stub=False).returncode == 0
    exported = "\n".join(collector.raw_texts())
    assert "api.z.ai" not in exported
