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
        "## About",
        "## Install",
        "## Trace a chat completion",
        "### Coding Plan is not this page",
        "### Z.ai's own SDK is not traced",
        "## What you get",
        "## What is not captured",
        "## Privacy",
        "## Run it yourself",
        "## Troubleshooting",
        "## How this differs from the OpenAI page",
    ):
        assert heading in page, heading
    assert page.startswith('---\ntitle: "Trace Z.ai chat completions"')


def test_the_page_states_version_url_and_provider_label(page):
    assert "traceAI-openai 0.1.10" in page
    assert page.count(f'base_url="{ZAI_URL}"') == 1
    assert "pip install traceAI-openai openai" in page
    assert "`openai`, not Z.ai" in page


def test_the_page_names_the_three_coding_plan_urls_and_zai_sdk(page):
    for url in CODING_PLAN_URLS:
        assert f"`{url}`" in page, url
    assert "zai-sdk" in page and "ZaiClient" in page
    assert "traceai-zai" in page  # said not to exist
    assert "pip install zai-sdk" not in page, "the recipe must not depend on zai-sdk"


def test_the_page_flags_the_stand_in_and_the_unverified_parts(page):
    assert "`STANDIN`" in page
    assert "Verified against the real Z.ai general platform" in page
    assert "Still not proven live" in page
    assert "Live vendor verification (2026-10-17)" in page


def test_the_page_names_every_hide_setting_the_example_uses(page):
    for name in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        assert name in page


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
