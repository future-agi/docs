"""Run both standalone scripts from the CometAPI page against loopback services."""
import base64
from importlib.metadata import version
import json
import re
import subprocess
import sys

from conftest import COMET_KEY, COMET_URL, FI_API_KEY, FI_SECRET_KEY, ROOT, clean_env, comet_requests, llm_spans

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "providers" / "cometapi.mdx"
PAGE_MODEL = "gpt-4o-mini"
QUESTION = "We accept unused packs within 30 days. Can I return an unused pack on day 12?"


def snippets():
    connection, returns = re.findall(r"```python\n(.*?)```", PAGE.read_text(), re.S)
    assert returns.count(f'base_url="{COMET_URL}"') == 1 and "chat.completions.create" in returns
    return connection, returns


def run(script, code, collector, **env_extra):
    env = clean_env()
    env.update(FI_API_KEY=FI_API_KEY, FI_SECRET_KEY=FI_SECRET_KEY, FI_BASE_URL=collector.url,
               FI_TRACES_URL=collector.url, OTEL_EXPORTER_OTLP_TRACES_TIMEOUT="3", NO_PROXY="127.0.0.1,localhost")
    env.update(env_extra)
    script.write_text(code)
    return subprocess.run([sys.executable, "-I", str(script)], cwd=script.parent, env=env, capture_output=True, text=True, timeout=120)


def test_connection_prints_the_exported_trace_id_without_inference(collector, probe, tmp_path):
    connection, _ = snippets()
    result = run(tmp_path / "comet_tracing.py", connection, collector, HTTPS_PROXY=probe.url)
    assert result.returncode == 0, result.stderr[-1500:]
    (span,) = collector.spans()
    assert span["name"] == "Check CometAPI trace export"
    assert span["_resource"]["project_name"] == "ridgeline-returns"
    assert span["_resource"]["project_type"] == "observe"
    assert base64.b64decode(span["trace_id"]).hex() in result.stdout.splitlines()
    assert not probe.seen


def test_the_page_snippet_runs_and_is_traced_on_the_named_project(stub, collector, tmp_path):
    _, returns = snippets()
    code = returns.replace(COMET_URL, stub.url)
    stub.stub.response_model = "resolved-test-model"
    result = run(tmp_path / "returns.py", code, collector, COMETAPI_KEY=COMET_KEY, COMETAPI_MODEL=PAGE_MODEL)
    assert result.returncode == 0, result.stderr[-1500:]
    (request,) = comet_requests(stub)
    assert request["body"]["model"] == PAGE_MODEL
    answer = f"echo: {QUESTION}"
    printed = json.loads(result.stdout.strip().splitlines()[-1])
    assert printed == {"answer": answer, "model": stub.stub.response_model,
                       "input_tokens": len(QUESTION.split()), "output_tokens": len(answer.split())}
    (span,) = llm_spans(collector)
    attrs = span["_attrs"]
    assert json.loads(attrs["gen_ai.request.parameters"])["model"] == PAGE_MODEL
    assert attrs["gen_ai.request.model"] == printed["model"]
    assert attrs["gen_ai.output.messages.0.message.content"] == printed["answer"]
    assert int(attrs["gen_ai.usage.input_tokens"]) == printed["input_tokens"]
    assert int(attrs["gen_ai.usage.output_tokens"]) == printed["output_tokens"]
    assert attrs["gen_ai.provider.name"] == "openai"
    assert span["_resource"]["project_name"] == "ridgeline-returns"
    assert span["_resource"]["project_type"] == "observe"


def test_the_page_snippet_as_written_dials_api_cometapi_com(collector, probe, tmp_path):
    _, returns = snippets()
    result = run(tmp_path / "returns.py", returns, collector, COMETAPI_KEY=COMET_KEY,
                 COMETAPI_MODEL=PAGE_MODEL, HTTPS_PROXY=probe.url)
    assert result.returncode != 0  # the probe refuses the tunnel, the snippet's request fails
    assert {p["target"] for p in probe.seen} == {"api.cometapi.com:443"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"
    # The standalone example also runs this test against its legacy adapter.
    assert span["_attrs"]["gen_ai.provider.name"] == ("openai" if version("traceAI-openai") == "0.1.10" else "cometapi")


def test_the_page_names_the_one_url_and_lists_what_it_does_not_cover():
    text = PAGE.read_text()
    _, returns = snippets()
    assert f'base_url="{COMET_URL}"' in returns
    assert f'export COMETAPI_MODEL="{PAGE_MODEL}"' in text
    assert "https://api.cometapi.com/v1/chat/completions" in text
    # The documented recipe is chat-only and does not promise a dedicated package.
    for route in ("Responses", "image", "video", "audio"):
        assert route in text
    assert "500+" not in text and "500 models" not in text
    assert "There is no `traceai-cometapi`" in text


def test_the_page_follows_the_docs_style_and_carries_no_secret():
    text = PAGE.read_text()
    assert chr(0x2014) not in text, "the docs style guide forbids em dashes"
    assert text.split("---", 2)[2].lstrip().startswith("## About")
    assert "'traceAI-openai==0.1.16' 'fi-instrumentation-otel==1.5.1' 'openai==3.57.0'" in text
    _, code = snippets()
    assert "finally:" in code and "provider.force_flush()" in code and "provider.shutdown()" in code
    assert 'COMETAPI_KEY="YOUR_COMETAPI_KEY"' in text  # placeholders only, no key in the page
    for name in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        assert name in text
    assert "Live vendor verification" not in text and "stand-in" not in text
    assert "error messages" in text and "tool definitions" in text
    assert "Under **Observe**, open **Tracing**" in text and "gen_ai.provider.name=cometapi" in text


def test_no_key_in_the_diff_and_no_other_cometapi_endpoint_client():
    """AC-04 / AC-05: no API key anywhere in the example or the page, and the example calls
    chat completions only (no image, video or Responses client)."""
    key_like = re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|[A-Za-z0-9]{32,})\b")
    files = [PAGE] + [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in {".py", ".sh", ".md", ".txt", ".ini"} and ".venv" not in p.parts and "__pycache__" not in p.parts]
    for path in files:
        for match in key_like.finditer(path.read_text()):
            raise AssertionError(f"{path}: looks like a key: {match.group(0)[:8]}...")
    app = (ROOT / "app.py").read_text()
    for forbidden in ("images.generate", "videos.", "responses.create", "audio."):
        assert forbidden not in app
