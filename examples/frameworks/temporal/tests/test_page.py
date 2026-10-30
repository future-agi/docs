"""The docs page stays true to the example: shown code is real code, and the promises it makes are in the files."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "..")
PAGE = os.path.join(EXAMPLE, "..", "..", "..", "src", "pages", "docs", "integrations", "frameworks", "temporal.mdx")


def page() -> str:
    return open(PAGE).read()


def code_blocks(text: str) -> list[tuple[str, str]]:
    return re.findall(r"```(\w+)\n(.*?)```", text, flags=re.S)


def test_every_python_excerpt_is_verbatim_and_in_order():
    checked = 0
    for lang, body in code_blocks(page()):
        first, _, rest = body.partition("\n")
        match = re.match(r"# file: (\S+)$", first)
        if lang != "python" or not match:
            continue
        # indentation is ignored: the page shows the body of main() without its indent
        lines = [line.strip() for line in open(os.path.join(EXAMPLE, match.group(1))).read().splitlines()]
        position = 0
        for shown in (line.strip() for line in rest.splitlines()):
            if not shown.strip() or shown.strip() == "...":
                continue
            try:
                position = lines.index(shown, position) + 1
            except ValueError:
                raise AssertionError(f"{match.group(1)}: line not found in order: {shown!r}") from None
        checked += 1
    assert checked >= 5


def test_front_matter_and_sections():
    text = page()
    assert text.startswith("---\ntitle: ")
    assert re.search(r'^description: ".+"$', text, flags=re.M)
    for heading in ("## About", "## Set up", "## What you see in Observe", "## Privacy", "## Flush on shutdown", "## Troubleshooting", "## Scope"):
        assert heading in text


def test_page_states_the_example_version_and_plugin_requirements():
    text = page()
    assert "**1.34.0**" in text
    assert '"temporalio[opentelemetry]==1.34.0"' in text
    assert "add_temporal_spans=True" in text and "default is `False`" in text
    assert "experimental" in text
    assert "create_tracer_provider(sampler, resource, shutdown_on_exit, active_span_processor, id_generator, span_limits)" in text
    assert "examples/frameworks/temporal" in text
    assert "Everything on this page was run end to end" not in text


def test_page_documents_the_headers_project_compression_and_privacy_switches():
    text = page()
    for needle in ("X-Api-Key", "X-Secret-Key", "project_name", "project_type", "NoCompression", "KEEP_TEMPORAL_ERROR_TEXT",
                   "FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_INPUT_MESSAGES", "FI_HIDE_OUTPUT_MESSAGES", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        assert needle in text, needle


def test_page_is_customer_application_tracing_and_links_no_internal_worker_code():
    text = page()
    assert "Temporal Python SDK" in text
    for internal in ("otel_sync_to_async", "bind_context", "futureagi/", "tfc/", "/Users/"):
        assert internal not in text, internal


def test_the_environment_variables_the_page_names_are_read_by_the_example():
    sources = "".join(open(os.path.join(EXAMPLE, f)).read() for f in ("tracing.py", "worker.py", "starter.py"))
    for name in ("FI_API_KEY", "FI_SECRET_KEY", "FI_BASE_URL", "FI_PROJECT_NAME", "KEEP_TEMPORAL_ERROR_TEXT", "TEMPORAL_ADDRESS", "TEMPORAL_NAMESPACE"):
        assert name in sources, name
