"""The docs page shows the shipped files, not a hand-edited copy of them."""
import re
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent
PAGE = EXAMPLE.parents[2] / "src/pages/docs/integrations/frameworks/watsonx-orchestrate-adk.mdx"
TEXT = PAGE.read_text()
BLOCKS = re.findall(r"^```(\w+)\n(.*?)^```", TEXT, flags=re.M | re.S)


def _blocks(lang: str) -> list[str]:
    return [body for kind, body in BLOCKS if kind == lang]


def test_page_shows_the_collector_config_verbatim():
    assert (EXAMPLE / "otelcol.yaml").read_text() in _blocks("yaml")


def test_every_python_line_on_the_page_is_in_the_example():
    source = {line.rstrip() for line in (EXAMPLE / "agent.py").read_text().splitlines()}
    blocks = _blocks("python")
    assert len(blocks) >= 5
    for block in blocks:
        for line in block.splitlines():
            if line.strip():
                assert line.rstrip() in source, line


def test_switches_and_variables_named_on_the_page_exist():
    config = (EXAMPLE / "otelcol.yaml").read_text()
    for name in ("KEEP_WXO_CONTENT", "FI_PROJECT_NAME", "FI_TRACES_URL", "FI_API_KEY", "FI_SECRET_KEY"):
        assert name in TEXT and name in config, name
    from ibm_watsonx_orchestrate_sdk.observability.attributes import ENV_OTLP_ENDPOINT

    assert ENV_OTLP_ENDPOINT == "WXO_OTLP_ENDPOINT" and ENV_OTLP_ENDPOINT in TEXT


def test_docker_command_on_the_page_matches_the_tested_image_and_env():
    bash = "\n".join(_blocks("bash"))
    assert "otel/opentelemetry-collector-contrib:0.162.0 --config /etc/otelcol.yaml" in bash
    assert "-e FI_API_KEY -e FI_SECRET_KEY" in bash  # values come from the shell, not the command line
    assert "WXO_OTLP_ENDPOINT=http://localhost:4318/v1/traces" in bash


def test_page_states_setup_privacy_and_scope():
    for needle in ("2.18.2", "0.162.0", "langgraph", "## Privacy", "## Troubleshooting", "## Scope",
                   "KEEP_WXO_CONTENT=true", "traceai-java-watsonx", "External Collector",
                   "exception stack traces", "private network", "examples/frameworks/watsonx-orchestrate-adk"):
        assert needle in TEXT, needle
    assert "How this was checked" not in TEXT
    assert "Everything on this page was run end to end" not in TEXT


def test_page_has_no_local_details():
    for needle in ("/Users/", "localhost:14338", "th8103", "gpt-5", "gpt-6", "127.0.0.1:8317"):
        assert needle not in TEXT, needle
