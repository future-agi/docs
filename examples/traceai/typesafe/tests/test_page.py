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


def test_page_install_and_tested_versions_match_requirements():
    page = _read(PAGE)
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([0-9.]+)", _read(os.path.join(HERE, "requirements.txt")), re.M))
    assert "typesafe-sdk **{0}**".format(pins["typesafe-sdk"]) in page
    assert "fi-instrumentation-otel {0}".format(pins["fi-instrumentation-otel"]) in page
    assert "pip install traceAI-typesafe typesafe-sdk" in page


def test_page_states_privacy_differences_and_the_stand_in():
    page = _read(PAGE)
    for needle in ("FI_HIDE_INPUTS=true", "FI_HIDE_OUTPUTS=true", "TraceConfig(hide_inputs=True)",
                   "TH-8183", "traceAI-openai", "EVALUATOR", "STANDIN", "Not supported", "Troubleshooting",
                   "never Pass/Fail", "models.list()"):
        assert needle in page, needle


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
