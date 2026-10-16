"""The Python snippet on the docs page, run as written.

The test reads the page, takes the code block that builds the client, swaps only the
BytePlus base URL for the local stand-in, and runs it in a separate process like a
customer would. A second run keeps the URL as written and sends it through the refusing
CONNECT probe to show which host the snippet dials."""
import re
import subprocess
import sys

from conftest import AP_URL, ARK_KEY, FI_API_KEY, FI_SECRET_KEY, ROOT, clean_env, llm_spans

PAGE = ROOT.parents[2] / "src" / "pages" / "docs" / "integrations" / "providers" / "byteplus.mdx"


def snippet():
    text = PAGE.read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    chosen = [b for b in blocks if AP_URL in b and "chat.completions.create" in b]
    assert len(chosen) == 1, "the page must have exactly one runnable Python recipe"
    return chosen[0]


def run(code, env_extra, tmp_path):
    env = clean_env()
    env.update({"ARK_API_KEY": ARK_KEY, "FI_API_KEY": FI_API_KEY, "FI_SECRET_KEY": FI_SECRET_KEY,
                "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "3", "PYTHONDONTWRITEBYTECODE": "1", "NO_PROXY": "127.0.0.1,localhost"})
    env.update(env_extra)
    script = tmp_path / "page_snippet.py"
    script.write_text(code + "\nimport time\ntrace_provider.force_flush()\ntrace_provider.shutdown()\n")
    return subprocess.run([sys.executable, "-I", str(script)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def test_the_page_snippet_runs_and_is_traced_on_the_named_project(stub, collector, tmp_path):
    code = snippet().replace(AP_URL, stub.url)
    result = run(code, {"FI_BASE_URL": collector.url}, tmp_path)
    assert result.returncode == 0, result.stderr[-1500:]
    assert "echo: What is the capital of France?" in result.stdout
    (span,) = llm_spans(collector)
    attrs = span["_attrs"]
    assert attrs["gen_ai.request.model"] == "your-model-or-endpoint-id"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert collector.spans()[0]["_resource"]["project_name"] == "my-chatbot"
    assert collector.spans()[0]["_resource"]["project_type"] == "observe"


def test_the_page_snippet_as_written_dials_the_asia_pacific_host(collector, probe, tmp_path):
    result = run(snippet(), {"FI_BASE_URL": collector.url, "HTTPS_PROXY": probe.url}, tmp_path)
    assert result.returncode != 0  # the probe refuses the tunnel, the snippet's request fails
    assert {p["target"] for p in probe.seen} == {"ark.ap-southeast.bytepluses.com:443"}
    (span,) = llm_spans(collector)
    assert span["status"]["code"] == "STATUS_CODE_ERROR"


def test_the_page_names_both_region_urls_and_the_coding_plan_warning():
    text = PAGE.read_text()
    assert "https://ark.eu-west.bytepluses.com/api/v3" in text
    assert "/api/coding" in text and "Coding Plan is not this page" in text
    assert chr(0x2014) not in text, "the docs style guide forbids em dashes"
    assert "ARK_API_KEY=\"YOUR_BYTEPLUS_ARK_API_KEY\"" in text  # placeholders only, no key in the page
