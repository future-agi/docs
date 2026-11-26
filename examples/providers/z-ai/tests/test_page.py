"""The docs page and the code on it.

The Python snippet on src/pages/docs/integrations/providers/z-ai.mdx is run exactly as written,
with only two substitutions (the placeholder model and the Z.ai base URL, which is swapped for the
local stand-in), and must produce the span the page describes."""
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
        "## Install",
        "## Trace a chat completion",
        "## View the trace",
        "## Privacy",
        "## Troubleshooting",
    ):
        assert heading in page, heading
    assert page.startswith('---\ntitle: "Trace Z.ai chat completions"')


def test_the_page_states_version_url_and_provider_label(page):
    assert page.count(f'base_url="{ZAI_URL}"') == 1
    assert "pip install traceAI-openai==0.1.10 openai==3.31.0" in page
    assert "**Provider shows `openai`:**" in page


def test_the_page_uses_the_general_platform_and_openai_client(page):
    assert "general platform API key" in page
    assert "https://docs.z.ai/devpack/quick-start" in page
    assert "rather than substituting `ZaiClient`" in page
    assert "pip install zai-sdk" not in page, "the recipe must not depend on zai-sdk"
    (code,) = [s for s in snippets(page, "python") if "OpenAIInstrumentor" in s]
    for url in CODING_PLAN_URLS:
        assert url not in code, "this example must use the general platform route"


def test_page_is_customer_facing_and_preserves_data_handling_guidance(page):
    for phrase in ("STANDIN", "Live vendor verification", "Still not proven live"):
        assert phrase not in page
    assert "request, response, and error content" in page
    assert "Use data approved for tracing" in page
    assert "illustrated with a sample trace" in page
    assert "/images/docs/integrations/z-ai-trace-view.png" in page


def test_optional_masking_links_to_the_client_guide_without_promising_error_redaction(page):
    assert "[OpenAI integration](/docs/integrations/traceai/openai)" in page
    assert "masking does not change what you send to Z.ai" in page
    assert "FI_HIDE_ERROR_DETAILS=true" not in page


def test_no_credentials_in_the_page_or_the_example():
    secrets = re.compile(r"(sk-[A-Za-z0-9]{16,}|Bearer [A-Za-z0-9._-]{20,}|[0-9a-f]{32}\.[A-Za-z0-9]{8,})")
    for path in [PAGE, *ROOT.rglob("*")]:
        if path.is_file() and path.suffix in {".mdx", ".py", ".sh", ".md", ".txt"} and ".venv" not in path.parts:
            assert not secrets.search(path.read_text()), path


def test_the_python_snippet_runs_as_written(page, stub, collector):
    (code,) = [s for s in snippets(page, "python") if "OpenAIInstrumentor" in s]
    assert code.count(f'base_url="{ZAI_URL}"') == 1 and code.count('model="your-model"') == 1
    code = code.replace(f'base_url="{ZAI_URL}"', f'base_url="{stub.url}"').replace('model="your-model"', f'model="{MODEL}"')
    code += "\ntrace_provider.force_flush()\ntrace_provider.shutdown()\n"
    env = clean_env()
    env.update(
        {
            "ZAI_API_KEY": ZAI_KEY,
            "FI_API_KEY": FI_API_KEY,
            "FI_SECRET_KEY": FI_SECRET_KEY,
            "FI_BASE_URL": collector.url,
            "NO_PROXY": "127.0.0.1,localhost",
            "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3",
        }
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, timeout=120, cwd="/")
    assert done.returncode == 0, done.stderr[-1500:]
    assert "Z.ai stand-in reply to: What is the capital of France?" in done.stdout
    (llm,) = llm_spans(collector)
    assert llm["_attrs"]["gen_ai.request.model"] == MODEL
    assert llm["_attrs"]["gen_ai.provider.name"] == "openai"
    assert llm["_resource"]["project_name"] == "my-chatbot"
    assert {kind(s) for s in collector.spans()} == {"LLM"}
