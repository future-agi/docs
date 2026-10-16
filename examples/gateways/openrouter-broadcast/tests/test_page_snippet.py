"""The docs page and the files in this directory must say the same thing."""
import json
import os
import re

import pytest
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PAGE = os.path.join(REPO, "src", "pages", "docs", "integrations", "gateways", "openrouter-broadcast.mdx")


@pytest.fixture(scope="module")
def page():
    with open(PAGE) as f:
        return f.read()


@pytest.fixture(scope="module")
def blocks(page):
    return re.findall(r"```(\w+)\n(.*?)```", page, flags=re.S)


def block(blocks, lang, contains):
    hits = [b for lang_, b in blocks if lang_ == lang and contains in b]
    assert hits, f"no {lang} block containing {contains!r}"
    return hits[0]


def test_frontmatter_and_first_heading(page):
    m = re.match(r'---\ntitle: "([^"]+)"\ndescription: "([^"]+)"\n---\n\n## About\n', page)
    assert m, "frontmatter, a blank line, then '## About'"
    assert 120 <= len(m.group(2)) <= 160, len(m.group(2))


def test_style_rules(page):
    assert "—" not in page and "–" not in page, "no em or en dashes"
    assert page.rstrip().split("\n## ")[-1].startswith("Next Steps")
    assert not re.search(r"\b(powerful|seamless|cutting-edge|game-changer)\b", page, re.I)


def test_the_yaml_on_the_page_is_otelcol_yaml(blocks):
    on_page = yaml.safe_load(block(blocks, "yaml", "bearertokenauth/broadcast"))
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        assert on_page == yaml.safe_load(f)


def test_docker_command_matches_the_config(page, blocks):
    cmd = block(blocks, "bash", "docker run")
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        text = f.read()
    needed = set(re.findall(r"\$\{env:([A-Z_]+)", text)) - {"FI_CAPTURE_CONTENT"}
    for name in needed:
        assert re.search(rf"-e {name}\b", cmd), name
    assert "otel/opentelemetry-collector-contrib:0.162.0" in cmd
    assert "--memory" in cmd and "-p 4318:4318" in cmd
    assert "/etc/otelcol/config.yaml" in cmd
    assert "FI_CAPTURE_CONTENT" not in cmd, "content stays off unless the reader opts in"


def test_every_environment_variable_is_explained(page):
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        names = set(re.findall(r"\$\{env:([A-Z_]+)", f.read()))
    for name in names:
        assert f"`{name}`" in page, name


def test_openrouter_headers_carry_the_collector_token_and_never_the_future_agi_keys(page):
    m = re.search(r"\| Headers \| `(\{.*?\})`", page)
    headers = json.loads(m.group(1).replace("YOUR_BROADCAST_TOKEN", "x"))
    assert list(headers) == ["Authorization"] and headers["Authorization"].startswith("Bearer ")
    assert "X-Api-Key" not in m.group(0) and "X-Secret-Key" not in m.group(0)


def test_the_removed_keys_the_page_lists_are_removed_by_the_config(page):
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        cfg = yaml.safe_load(f)
    statements = [s for b in cfg["processors"]["transform/openrouter"]["trace_statements"] for s in b["statements"]]
    regexes = []
    for s in statements:
        m = re.search(r'delete_matching_keys\(attributes, "((?:[^"\\]|\\.)*)"\)', s)
        if m:
            regexes.append(re.compile(json.loads(f'"{m.group(1)}"')))
    deleted = {m.group(1) for s in statements for m in [re.match(r'delete_key\(attributes, "([^"]+)"\)', s)] if m}
    section = page.split("With the collector default")[1].split("Kept:")[0]
    for key in re.findall(r"`((?:span|trace|gen_ai|exception)\.[a-z_.]+)`", section):
        assert key in deleted or any(r.search(key) for r in regexes), key


def test_no_secret_looking_value_on_the_page(page):
    assert not re.search(r"[0-9a-f]{24,}", page)
    assert "YOUR_API_KEY" in page and "YOUR_SECRET_KEY" in page


def test_internal_links_point_at_pages_that_exist(page):
    for href in set(re.findall(r"\]\((/docs/[^)#]+)", page)):
        rel = href[len("/docs/"):]
        candidates = [os.path.join(REPO, "src", "pages", "docs", rel + ".mdx"), os.path.join(REPO, "src", "pages", "docs", rel, "index.mdx")]
        assert any(os.path.exists(c) for c in candidates), href


def test_the_page_says_openrouter_was_not_run_and_names_the_stand_in(page):
    assert "Nobody ran OpenRouter" in page and "stand-in" in page
    assert "| OpenRouter | Not run." in page
