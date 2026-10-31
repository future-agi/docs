"""The docs page shows the shipped files, not a hand-edited copy of them."""
import re
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent
PAGE = EXAMPLE.parents[2] / "src/pages/docs/integrations/frameworks/restate.mdx"
TEXT = PAGE.read_text()
BLOCKS = re.findall(r"^```(\w+)\n(.*?)^```", TEXT, flags=re.M | re.S)


def _blocks(lang: str) -> list[str]:
    return [body for kind, body in BLOCKS if kind == lang]


def test_page_shows_the_collector_config_without_test_diary_comment():
    config = (EXAMPLE / "otelcol.yaml").read_text().replace(
        "# Tested with otel/opentelemetry-collector-contrib 0.162.0.\n#\n", ""
    )
    assert config in _blocks("yaml")
    assert "# Tested with" not in TEXT
    assert "@latest" not in TEXT
    assert "releases/tag/v1.8.0" in TEXT
    assert "releases/tag/v1.7.13" in TEXT


def test_page_shows_the_server_config_verbatim():
    assert (EXAMPLE / "restate.toml").read_text() in _blocks("toml")


def test_every_python_line_on_the_page_is_in_the_example():
    source = {line.rstrip() for line in (EXAMPLE / "agent_service.py").read_text().splitlines()}
    blocks = _blocks("python")
    assert len(blocks) >= 3
    for block in blocks:
        for line in block.splitlines():
            if line.strip():
                assert line.rstrip() in source, line


def test_switches_named_on_the_page_exist():
    from fi_instrumentation.instrumentation import config

    for name in re.findall(r"FI_HIDE_[A-Z_]+", TEXT):
        assert hasattr(config, name), name
    assert "KEEP_RESTATE_DETAILS" in (EXAMPLE / "otelcol.yaml").read_text()


def test_page_states_versions_privacy_and_limits():
    for needle in ("1.8.0", "1.7.13", "restate-sdk", "1.0.5", "0.162.0", "## Privacy", "## Troubleshooting",
                   "## Not covered", "outside this guide’s coverage", "KEEP_RESTATE_DETAILS=true"):
        assert needle in TEXT, needle


def test_page_links_complete_service_without_verification_diary():
    assert "examples/frameworks/restate/agent_service.py" in TEXT
    assert "not a standalone service" in TEXT
    assert "private network" in TEXT
    assert "Tested: with the five" not in TEXT
    assert "Everything on this page was run end to end" not in TEXT


def test_standard_serving_replaces_copied_lifecycle_code():
    source = (EXAMPLE / "agent_service.py").read_text()
    for obsolete in ("_let_sdk_install_sigterm_handler", "signal.signal", "add_signal_handler", "asyncio.serve"):
        assert obsolete not in source
        assert obsolete not in TEXT
    assert "python -m hypercorn agent_service:app --workers 1" in TEXT
    assert "--graceful-timeout 30" in TEXT
    assert "--workers 0" in TEXT
    assert "SIGKILL" in TEXT
    entry = re.search(r"os\.execv\(.*?\]\)", source, flags=re.S).group(0)
    for arg in ('"--workers", "1"', '"--graceful-timeout", "30"'):
        assert arg in entry


def test_page_has_no_local_details():
    for needle in ("/Users/", "localhost:14338", "th8103", "gpt-6"):
        assert needle not in TEXT, needle
