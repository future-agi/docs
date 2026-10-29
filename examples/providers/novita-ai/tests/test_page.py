"""The Python snippet on the docs page, run as written.

The test reads the page, takes the code block that builds the client, swaps only the Novita base
URL for the local stand-in, and runs it in a separate process like a customer would. A second run
keeps the URL as written and sends it through the refusing CONNECT probe to show which host the
snippet dials. The remaining tests keep the page and the example app saying the same thing."""
import re
import subprocess
import sys

from conftest import FI_API_KEY, FI_SECRET_KEY, NOVITA_BARE_URL, NOVITA_KEY, NOVITA_URL, ROOT, clean_env, llm_spans, novita_requests

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "providers" / "novita-ai.mdx"


def snippet():
    text = PAGE.read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    chosen = [b for b in blocks if NOVITA_URL in b and "chat.completions.create" in b]
    assert len(chosen) == 1, "the page must have exactly one runnable Python recipe"
    return chosen[0]


def run(code, env_extra, tmp_path):
    env = clean_env()
    env.update({"NOVITA_API_KEY": NOVITA_KEY, "FI_API_KEY": FI_API_KEY, "FI_SECRET_KEY": FI_SECRET_KEY,
                "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3", "PYTHONDONTWRITEBYTECODE": "1", "NO_PROXY": "127.0.0.1,localhost"})
    env.update(env_extra)
    script = tmp_path / "page_snippet.py"
    script.write_text(code + "\ntrace_provider.force_flush()\ntrace_provider.shutdown()\n")
    return subprocess.run([sys.executable, "-I", str(script)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def test_the_page_snippet_runs_and_is_traced_on_the_named_project(stub, collector, tmp_path):
    code = snippet().replace(NOVITA_URL, stub.url)
    result = run(code, {"FI_BASE_URL": collector.url}, tmp_path)
    assert result.returncode == 0, result.stderr[-1500:]
    assert "echo: What is the capital of France?" in result.stdout
    (span,) = llm_spans(collector)
    attrs = span["_attrs"]
    assert attrs["gen_ai.request.model"] == "your-model-id"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert collector.spans()[0]["_resource"]["project_name"] == "my-chatbot"
    assert collector.spans()[0]["_resource"]["project_type"] == "observe"
    (request,) = novita_requests(stub)
    assert request["path"] == "/openai/v1/chat/completions" and request["body"]["max_tokens"] == 128


def test_the_page_snippet_as_written_dials_api_novita_ai(collector, probe, tmp_path):
    result = run(snippet(), {"FI_BASE_URL": collector.url, "HTTPS_PROXY": probe.url}, tmp_path)
    assert result.returncode != 0  # the probe refuses the tunnel, the snippet's request fails
    assert {p["target"] for p in probe.seen} == {"api.novita.ai:443"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"


def test_the_page_and_the_app_agree_on_the_recipe_url(stub):
    import importlib.util

    spec = importlib.util.spec_from_file_location("recipe_app", ROOT / "app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    assert app.NOVITA_BASE_URL == NOVITA_URL
    assert f'base_url="{NOVITA_URL}"' in snippet()


def test_the_page_names_every_url_form_and_keeps_secrets_out():
    text = PAGE.read_text()
    for form in (NOVITA_URL, NOVITA_BARE_URL, "https://api.novita.ai/v3/openai"):
        assert f"`{form}`" in text
    assert "## Which base URL" in text
    assert chr(0x2014) not in text, "the docs style guide forbids em dashes"
    assert 'NOVITA_API_KEY="YOUR_NOVITA_API_KEY"' in text  # placeholders only, no key in the page
    assert not re.search(r"sk[-_][A-Za-z0-9]{16,}", text)


def test_the_page_records_the_live_run_and_does_not_claim_a_novita_provider_label():
    text = PAGE.read_text()
    assert "## Live vendor verification (2026-10-18)" in text
    assert "no request was sent" not in text
    assert "`openai`, not Novita" in text
