"""Where the unmodified recipe client dials when it uses the documented BytePlus URLs.

No request leaves the machine: HTTPS_PROXY points at a probe that records the
`CONNECT host:port` the client asks for and answers 403. That is the strongest
statement possible about the BytePlus hosts without a BytePlus account: the
documented base URL makes the OpenAI client dial exactly that host, on 443."""
import pytest
from conftest import kind, llm_spans

AP_HOST = "ark.ap-southeast.bytepluses.com:443"
EU_HOST = "ark.eu-west.bytepluses.com:443"


@pytest.mark.parametrize("region, host", [("ap", AP_HOST), ("eu", EU_HOST)])
def test_the_documented_url_dials_exactly_that_region(run_app, collector, probe, region, host):
    result = run_app(
        "--scenario", "chat", env={"ARK_REGION": region, "HTTPS_PROXY": probe.url}, use_stub=False
    )
    assert result.returncode == 0, result.stderr[-1500:]
    assert "RESULT chat: APIConnectionError" in result.stdout
    assert probe.seen, "the client never tried to connect"
    assert {p["target"] for p in probe.seen} == {host}
    assert {p["method"] for p in probe.seen} == {"CONNECT"}
    other = EU_HOST if host == AP_HOST else AP_HOST
    assert other not in {p["target"] for p in probe.seen}, "the recipe must not fall back to the other region"


def test_the_default_region_is_asia_pacific(run_app, probe):
    assert run_app("--scenario", "chat", env={"HTTPS_PROXY": probe.url}, use_stub=False).returncode == 0
    assert {p["target"] for p in probe.seen} == {AP_HOST}


@pytest.mark.parametrize("region", ["ap", "eu"])
def test_either_region_url_is_traced_by_the_same_instrumentor(run_app, collector, probe, region):
    assert run_app("--scenario", "chat", env={"ARK_REGION": region, "HTTPS_PROXY": probe.url}, use_stub=False).returncode == 0
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"
    assert "APIConnectionError" in span["status"]["message"]
    assert span["_attrs"]["gen_ai.provider.name"] == "openai"
    assert span["_attrs"]["gen_ai.span.kind"] == "LLM"
    assert collector.spans()[0]["_resource"]["project_name"] == "byteplus-test"
    assert {kind(s) for s in collector.spans()} == {"AGENT", "LLM"}


def test_the_span_does_not_record_the_base_url_or_region(run_app, collector, probe):
    assert run_app("--scenario", "chat", env={"HTTPS_PROXY": probe.url}, use_stub=False).returncode == 0
    exported = "\n".join(collector.raw_texts())
    assert "bytepluses" not in exported
    assert "ap-southeast" not in exported
