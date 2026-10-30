"""The Python snippet on the docs page, run as written, and what the page promises.

The test reads the page, takes the code block that builds the client, swaps only the
CometAPI base URL for the local stand-in, and runs it in a separate process like a
customer would. A second run keeps the URL as written and sends it through the refusing
CONNECT probe to show which host the snippet dials."""
import re
import subprocess
import sys

from conftest import COMET_KEY, COMET_URL, FI_API_KEY, FI_SECRET_KEY, ROOT, clean_env, llm_spans

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "providers" / "cometapi.mdx"


def snippet():
    text = PAGE.read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    chosen = [b for b in blocks if COMET_URL in b and "chat.completions.create" in b]
    assert len(chosen) == 1, "the page must have exactly one runnable Python recipe"
    return chosen[0]


def run(code, env_extra, tmp_path):
    env = clean_env()
    env.update({"COMETAPI_KEY": COMET_KEY, "FI_API_KEY": FI_API_KEY, "FI_SECRET_KEY": FI_SECRET_KEY,
                "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3", "PYTHONDONTWRITEBYTECODE": "1", "NO_PROXY": "127.0.0.1,localhost"})
    env.update(env_extra)
    script = tmp_path / "page_snippet.py"
    script.write_text(code + "\ntrace_provider.force_flush()\ntrace_provider.shutdown()\n")
    return subprocess.run([sys.executable, "-I", str(script)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def test_the_page_snippet_runs_and_is_traced_on_the_named_project(stub, collector, tmp_path):
    code = snippet().replace(COMET_URL, stub.url)
    result = run(code, {"FI_BASE_URL": collector.url}, tmp_path)
    assert result.returncode == 0, result.stderr[-1500:]
    assert "echo: What is the capital of France?" in result.stdout
    (span,) = llm_spans(collector)
    attrs = span["_attrs"]
    assert attrs["gen_ai.request.model"] == "your-model-id"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert collector.spans()[0]["_resource"]["project_name"] == "my-chatbot"
    assert collector.spans()[0]["_resource"]["project_type"] == "observe"


def test_the_page_snippet_as_written_dials_api_cometapi_com(collector, probe, tmp_path):
    result = run(snippet(), {"FI_BASE_URL": collector.url, "HTTPS_PROXY": probe.url}, tmp_path)
    assert result.returncode != 0  # the probe refuses the tunnel, the snippet's request fails
    assert {p["target"] for p in probe.seen} == {"api.cometapi.com:443"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"


def test_the_page_names_the_one_url_and_lists_what_it_does_not_cover():
    text = PAGE.read_text()
    assert text.count("https://api.cometapi.com/v1") >= 3
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
    assert 'COMETAPI_KEY="YOUR_COMETAPI_KEY"' in text  # placeholders only, no key in the page
    for name in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        assert name in text
    assert "Live vendor verification" not in text and "stand-in" not in text
    assert "error messages" in text and "tool definitions" in text
    assert "Open **Observe**" in text and "traceAI-openai 0.1.10" in text


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
