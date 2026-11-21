"""The docs page and the code on it.

The Python snippet on src/pages/docs/integrations/providers/z-ai.mdx is run exactly as written,
with the Z.ai base URL swapped for the local stand-in and a configured model, and must produce the span the page describes."""
from importlib.metadata import version
import re
import subprocess
import sys

import pytest
from conftest import CODING_PLAN_URLS, FI_API_KEY, FI_SECRET_KEY, MODEL, ROOT, ZAI_KEY, ZAI_URL, clean_env, kind, llm_spans

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "providers" / "z-ai.mdx"


@pytest.fixture(scope="module")
def page():
    return PAGE.read_text()


def snippets(text, lang):
    return re.findall(rf"```{lang}\n(.*?)```", text, flags=re.S)


def test_the_page_has_the_required_sections(page):
    for heading in (
        "## About",
        "## Configure the endpoint",
        "## Send the return question",
        "## Limits and troubleshooting",
        "## Next steps",
    ):
        assert heading in page, heading
    assert page.startswith('---\ntitle: "Trace Z.ai chat completions"')


def test_the_page_states_version_url_and_provider_label(page):
    assert page.count(f'base_url="{ZAI_URL}"') == 1
    assert "'traceAI-openai==0.1.16' 'fi-instrumentation-otel==1.5.1' 'openai==3.57.0'" in page
    assert "`gen_ai.provider.name` is `zai`" in page


def test_the_page_uses_the_general_platform_and_openai_client(page):
    assert "general platform API key" in page
    assert "https://docs.z.ai/devpack/quick-start" in page
    assert "not `ZaiClient`" in page
    assert "pip install zai-sdk" not in page, "the recipe must not depend on zai-sdk"
    (code,) = [s for s in snippets(page, "python") if "OpenAIInstrumentor" in s]
    for url in CODING_PLAN_URLS:
        assert url not in code, "this example must use the general platform route"


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


@pytest.mark.parametrize("original_host", [False, True], ids=["loopback-success", "original-host-refused"])
def test_the_python_snippet_runs_as_written(page, stub, collector, probe, original_host):
    (code,) = [s for s in snippets(page, "python") if "OpenAIInstrumentor" in s]
    assert code.count(f'base_url="{ZAI_URL}"') == 1 and code.count('model=os.environ["ZAI_MODEL"]') == 1
    if not original_host:
        code = code.replace(f'base_url="{ZAI_URL}"', f'base_url="{stub.url}"')
    env = clean_env()
    env.update(
        {
            "ZAI_API_KEY": ZAI_KEY,
            "ZAI_MODEL": MODEL,
            "FI_API_KEY": FI_API_KEY,
            "FI_SECRET_KEY": FI_SECRET_KEY,
            "FI_BASE_URL": collector.url,
            "NO_PROXY": "127.0.0.1,localhost",
            "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3",
        }
    )
    if original_host:
        env["HTTPS_PROXY"] = probe.url
    done = subprocess.run([sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, timeout=120, cwd="/")
    if original_host:
        assert done.returncode != 0
        assert {p["target"] for p in probe.seen} == {"api.z.ai:443"}
        (failed,) = llm_spans(collector)
        assert failed["status"]["code"] == "STATUS_CODE_ERROR"
        assert failed["_attrs"]["gen_ai.provider.name"] == ("openai" if version("traceAI-openai") == "0.1.10" else "zai")
        return
    assert done.returncode == 0, done.stderr[-1500:]
    assert "Z.ai stand-in reply to: We accept unused packs within 30 days. Can I return an unused pack on day 12?" in done.stdout
    (llm,) = llm_spans(collector)
    assert llm["_attrs"]["gen_ai.request.model"] == MODEL
    assert llm["_attrs"]["gen_ai.provider.name"] == "openai"
    assert llm["_resource"]["project_name"] == "ridgeline-returns"
    assert {kind(s) for s in collector.spans()} == {"LLM"}
