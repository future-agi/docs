"""Run both Python files from the Z.ai page with a loopback collector and provider."""
import base64
from importlib.metadata import version
import json
import re
import subprocess
import sys

import pytest
from conftest import CODING_PLAN_URLS, FI_API_KEY, FI_SECRET_KEY, ROOT, ZAI_KEY, ZAI_URL, clean_env, kind, llm_spans, zai_requests

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "providers" / "z-ai.mdx"
PAGE_MODEL = "glm-4.5-flash"
QUESTION = "We accept unused packs within 30 days. Can I return an unused pack on day 12?"


@pytest.fixture(scope="module")
def page():
    return PAGE.read_text()


def snippets(text, lang):
    return re.findall(rf"```{lang}\n(.*?)```", text, flags=re.S)


@pytest.fixture
def scripts(page, tmp_path):
    tracing, returns = snippets(page, "python")
    assert returns.count(f'base_url="{ZAI_URL}"') == 1
    assert returns.count('model=os.environ["ZAI_MODEL"]') == 1
    for url in CODING_PLAN_URLS:
        assert url not in tracing and url not in returns, "this example must use the general platform route"
    (tmp_path / "tracing.py").write_text(tracing)
    (tmp_path / "returns.py").write_text(returns)
    return tmp_path


def run(script, collector, **env_extra):
    env = clean_env()
    env.update(FI_API_KEY=FI_API_KEY, FI_SECRET_KEY=FI_SECRET_KEY, FI_BASE_URL=collector.url,
               FI_TRACES_URL=collector.url, OTEL_EXPORTER_OTLP_TRACES_TIMEOUT="3", NO_PROXY="127.0.0.1,localhost")
    env.update(env_extra)
    # Ignore ambient Python settings and user packages, but allow the documented sibling import.
    return subprocess.run([sys.executable, "-E", "-s", script.name], cwd=script.parent, env=env,
                          capture_output=True, text=True, timeout=120)


def test_the_page_has_the_required_sections(page):
    for heading in (
        "## About",
        "## Configure the endpoint",
        "## Connect to Observe",
        "## Send the return question",
        "## Limits and troubleshooting",
        "## Next steps",
    ):
        assert heading in page, heading
    assert page.startswith('---\ntitle: "Trace Z.ai chat completions"')


def test_the_page_states_version_url_and_provider_label(page):
    assert page.count(f'base_url="{ZAI_URL}"') == 1
    assert f'export ZAI_MODEL="{PAGE_MODEL}"' in page
    assert "'traceAI-openai==0.1.16' 'fi-instrumentation-otel==1.5.1' 'openai==3.57.0'" in page
    assert "`gen_ai.provider.name` is `zai`" in page


def test_the_page_uses_the_general_platform_and_openai_client(page):
    assert "general platform API key" in page
    assert "https://docs.z.ai/devpack/quick-start" in page
    assert "not `ZaiClient`" in page
    assert "pip install zai-sdk" not in page, "the recipe must not depend on zai-sdk"


def test_page_is_customer_facing_and_preserves_data_handling_guidance(page):
    for phrase in ("STANDIN", "Live vendor verification", "Still not proven live"):
        assert phrase not in page
    assert "Request, response and error content" in page
    assert "Use data approved for tracing" in page
    assert "The OpenAI example below shows where to find the control" in page
    assert "/images/docs/integrations/z-ai-trace-view.png" in page


def test_optional_masking_documents_independent_error_control(page):
    assert "(/docs/integrations/traceai/openai)" in page
    assert "masking does not change what you send to Z.ai" in page
    assert "FI_HIDE_ERROR_DETAILS=true" in page


def test_no_credentials_in_the_page_or_the_example():
    secrets = re.compile(r"(sk-[A-Za-z0-9]{16,}|Bearer [A-Za-z0-9._-]{20,}|[0-9a-f]{32}\.[A-Za-z0-9]{8,})")
    for path in [PAGE, *ROOT.rglob("*")]:
        if path.is_file() and path.suffix in {".mdx", ".py", ".sh", ".md", ".txt"} and ".venv" not in path.parts:
            assert not secrets.search(path.read_text()), path


def test_connection_prints_the_exported_trace_id_without_inference(scripts, collector, probe):
    done = run(scripts / "tracing.py", collector, HTTPS_PROXY=probe.url)
    assert done.returncode == 0, done.stderr[-1500:]
    (span,) = collector.spans()
    assert span["name"] == "zai.connection"
    assert span["_resource"]["project_name"] == "ridgeline-returns"
    assert base64.b64decode(span["trace_id"]).hex() in done.stdout.splitlines()
    assert not probe.seen


@pytest.mark.parametrize("original_host", [False, True], ids=["loopback-success", "original-host-refused"])
def test_the_python_snippet_runs_as_written(scripts, stub, collector, probe, original_host):
    script = scripts / "returns.py"
    if not original_host:
        script.write_text(script.read_text().replace(ZAI_URL, stub.url))
        stub.stub.response_model = "glm-resolved-test-model"
    done = run(script, collector, ZAI_API_KEY=ZAI_KEY, ZAI_MODEL=PAGE_MODEL, HTTPS_PROXY=probe.url)
    if original_host:
        assert done.returncode != 0
        assert {p["target"] for p in probe.seen} == {"api.z.ai:443"}
        (failed,) = llm_spans(collector)
        assert failed["status"]["code"] == "STATUS_CODE_ERROR"
        assert failed["_attrs"]["gen_ai.provider.name"] == ("openai" if version("traceAI-openai") == "0.1.10" else "zai")
        return
    assert done.returncode == 0, done.stderr[-1500:]
    assert not probe.seen
    (request,) = zai_requests(stub)
    assert request["body"]["model"] == PAGE_MODEL
    answer = f"Z.ai stand-in reply to: {QUESTION}"
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result == {
        "answer": answer,
        "model": stub.stub.response_model,
        "input_tokens": len(QUESTION.split()),
        "output_tokens": len(answer.split()),
    }
    (llm,) = llm_spans(collector)
    attrs = llm["_attrs"]
    assert json.loads(attrs["gen_ai.request.parameters"])["model"] == PAGE_MODEL
    assert attrs["gen_ai.request.model"] == result["model"]
    assert attrs["gen_ai.output.messages.0.message.content"] == result["answer"]
    assert int(attrs["gen_ai.usage.input_tokens"]) == result["input_tokens"]
    assert int(attrs["gen_ai.usage.output_tokens"]) == result["output_tokens"]
    assert attrs["gen_ai.provider.name"] == "openai"
    assert llm["_resource"]["project_name"] == "ridgeline-returns"
    assert {kind(s) for s in collector.spans()} == {"LLM"}
