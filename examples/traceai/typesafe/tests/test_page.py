"""The docs page and this example agree; no network."""

from __future__ import annotations

import os
import re
import textwrap

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.normpath(os.path.join(HERE, "..", "..", "..", "src", "pages", "docs", "integrations", "traceai", "typesafe.mdx"))


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _blocks(language):
    return re.findall(r"```{0}\n(.*?)```".format(language), _read(PAGE), re.S)


def _excerpt(name):
    match = re.search(r"# --- {0} start ---\n(.*?)\s*# --- {0} end ---".format(name), _read(os.path.join(HERE, "app.py")), re.S)
    assert match, name
    return textwrap.dedent(match.group(1)).strip()


def test_every_page_snippet_from_the_app_is_an_exact_excerpt():
    blocks = [block.strip() for block in _blocks("python")]
    for name in ("recipe", "questions", "sync call", "async call"):
        assert _excerpt(name) in blocks, name


def test_page_install_and_supported_range():
    page = _read(PAGE)
    assert "pip install traceAI-typesafe typesafe-sdk" in page
    assert "Python 3.10 to 3.13, as required by `traceAI-typesafe` 0.1.0" in page
    assert "`typesafe-sdk` 0.7.0 or later, below 1.0" in page
    assert "fi-instrumentation-otel does not support" not in page


def test_page_snippets_define_what_they_use():
    questions = next(block for block in _blocks("python") if "QUESTIONS = {" in block)
    assert questions.lstrip().startswith("TICKET = (")
    assert "MARKER" not in _read(PAGE)


def test_page_states_privacy_and_scope():
    page = _read(PAGE)
    for needle in ("FI_HIDE_INPUTS=true", "FI_HIDE_OUTPUTS=true", "TraceConfig(hide_inputs=True)",
                   "traceAI-openai", "EVALUATOR", "Not supported", "Troubleshooting",
                   "never turns answers into Pass/Fail", "models.list()"):
        assert needle in page, needle


def test_page_has_no_internal_test_material():
    page = _read(PAGE)
    for needle in ("STANDIN", "stand-in", "run_e2e.sh", "Live vendor verification", "fi_verify",
                   "TH-8183", "2026-", "rows_hit", "PASS"):
        assert needle not in page, needle
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", page)


def test_page_does_not_send_customers_to_another_platform_by_default():
    page = _read(PAGE)
    assert "base_url=\"https://api.typesafe.ai\"" not in page
    assert "pip install typesafe-ai" not in page and "pip install jev" not in page


def test_run_script_never_prints_keys():
    script = _read(os.path.join(HERE, "run_e2e.sh"))
    for name in ("FI_API_KEY", "FI_SECRET_KEY", "TYPESAFE_API_KEY"):
        assert not re.search(r"echo[^\n]*\$\{?" + name, script), name
    assert "set -euo pipefail" in script


def test_stand_in_is_labelled():
    stub = _read(os.path.join(HERE, "standin", "systemone_stub.py"))
    assert "NOT TypeSafe" in stub and "127.0.0.1" in stub
