"""Run both Python files from the Novita page with a loopback collector and provider."""
import base64
from importlib.metadata import version
import json
import re
import subprocess
import sys

import pytest
from conftest import FI_API_KEY, FI_SECRET_KEY, MODEL, NOVITA_BARE_URL, NOVITA_KEY, NOVITA_URL, ROOT, clean_env, llm_spans, novita_requests

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "providers" / "novita-ai.mdx"


def snippets():
    tracing, returns = re.findall(r"```python\n(.*?)```", PAGE.read_text(), re.S)
    return tracing, returns


@pytest.fixture
def scripts(tmp_path):
    tracing, returns = snippets()
    assert returns.count(f'base_url="{NOVITA_URL}"') == 1
    assert returns.count('model=os.environ["NOVITA_MODEL"]') == 1
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


def test_connection_prints_the_exported_trace_id_without_inference(scripts, collector, probe):
    result = run(scripts / "tracing.py", collector, HTTPS_PROXY=probe.url)
    assert result.returncode == 0, result.stderr[-1500:]
    (span,) = collector.spans()
    assert span["name"] == "novita.connection"
    assert span["_resource"]["project_name"] == "ridgeline-returns"
    assert base64.b64decode(span["trace_id"]).hex() in result.stdout.splitlines()
    assert not probe.seen


def test_the_page_snippet_runs_and_is_traced_on_the_named_project(stub, collector, scripts):
    script = scripts / "returns.py"
    script.write_text(script.read_text().replace(NOVITA_URL, stub.url))
    stub.stub.response_model = "resolved-test-model"
    result = run(script, collector, NOVITA_API_KEY=NOVITA_KEY, NOVITA_MODEL=MODEL)
    assert result.returncode == 0, result.stderr[-1500:]
    assert "echo: We accept unused packs within 30 days. Can I return an unused pack on day 12?" in result.stdout.splitlines()
    (span,) = llm_spans(collector)
    attrs = span["_attrs"]
    assert json.loads(attrs["gen_ai.request.parameters"])["model"] == MODEL
    assert attrs["gen_ai.request.model"] == stub.stub.response_model
    assert attrs["gen_ai.provider.name"] == "openai"
    assert span["_resource"]["project_name"] == "ridgeline-returns"
    assert span["_resource"]["project_type"] == "observe"
    (request,) = novita_requests(stub)
    assert request["path"] == "/openai/v1/chat/completions" and request["body"]["max_tokens"] == 128
    assert request["body"]["model"] == MODEL


def test_the_page_snippet_as_written_dials_api_novita_ai(collector, probe, scripts):
    result = run(scripts / "returns.py", collector, NOVITA_API_KEY=NOVITA_KEY, NOVITA_MODEL=MODEL, HTTPS_PROXY=probe.url)
    assert result.returncode != 0  # the probe refuses the tunnel, the snippet's request fails
    assert {p["target"] for p in probe.seen} == {"api.novita.ai:443"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"
    # The standalone example also runs this test against its legacy adapter.
    assert span["_attrs"]["gen_ai.provider.name"] == ("openai" if version("traceAI-openai") == "0.1.10" else "novita")


def test_the_page_and_the_app_agree_on_the_recipe_url():
    import importlib.util

    spec = importlib.util.spec_from_file_location("recipe_app", ROOT / "app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    assert app.NOVITA_BASE_URL == NOVITA_URL
    _, returns = snippets()
    assert f'base_url="{NOVITA_URL}"' in returns


def test_the_page_names_every_url_form_and_keeps_secrets_out():
    text = PAGE.read_text()
    for form in (NOVITA_URL, NOVITA_BARE_URL):
        assert f"`{form}`" in text
    assert "## Configure the endpoint" in text
    assert chr(0x2014) not in text, "the docs style guide forbids em dashes"
    assert 'NOVITA_API_KEY="YOUR_NOVITA_API_KEY"' in text  # placeholders only, no key in the page
    assert not re.search(r"sk[-_][A-Za-z0-9]{16,}", text)


def test_the_page_explains_privacy_and_provider_label_without_a_test_diary():
    text = PAGE.read_text()
    assert "Live vendor verification" not in text and "stand-in" not in text
    assert "gen_ai.provider.name=novita" in text
    assert "Under **Observe**, open **Tracing**" in text
    assert "'traceAI-openai==0.1.16' 'fi-instrumentation-otel==1.5.1' 'openai==3.57.0'" in text
    assert "unknown proxy hostname keeps `openai`" in text
    _, returns = snippets()
    assert "finally:" in returns and "provider.force_flush()" in returns and "provider.shutdown()" in returns
    for name in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        assert name in text
    assert "error messages" in text and "tool definitions" in text
