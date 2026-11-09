"""Pin the native destination contract, not the retired on-page collector recipe.

The collector's defensive behavior remains covered by test_otelcol_config.py.
These checks do not claim that a real OpenRouter destination delivered a trace.
"""
import json
import os
import re

import pytest

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


def test_frontmatter_and_first_heading(page):
    m = re.match(r'---\ntitle: "([^"]+)"\ndescription: "([^"]+)"\n---\n\n## About\n', page)
    assert m
    assert 120 <= len(m.group(2)) <= 160


def test_native_destination_headers(blocks, page):
    headers = json.loads(next(b for lang, b in blocks if lang == "json"))
    assert headers == {
        "X-Api-Key": "YOUR_API_KEY",
        "X-Secret-Key": "YOUR_SECRET_KEY",
        "X-Project-Name": "my-openrouter",
    }
    assert "https://api.futureagi.com/tracer/v1/traces" in page
    assert "OTLP/HTTP with JSON encoding" in page
    assert "docker run" not in page
    assert not any(lang == "yaml" for lang, _ in blocks)


def test_catalog_matches_the_native_route():
    with open(os.path.join(REPO, "src", "lib", "integrations.mjs")) as f:
        row = next(line for line in f if "id: 'openrouter-broadcast'" in line)
    assert "directly with an endpoint and three headers" in row
    assert "privacy-filtering collector" not in row


def test_project_header_contract_is_self_contained(page):
    for text in ("resource attribute takes precedence", "255 characters", "without commas",
                 "control characters", "invisible characters", "repeated project-name headers",
                 "key pair selects the workspace", "older collectors require an upgrade"):
        assert text in page
    # The general header-reference PR is still open. Do not link its absent anchor.
    assert "export-formats#naming-the-project" not in page


def test_application_request_is_small_and_uses_separate_credentials(blocks, page):
    cmd = next(b for lang, b in blocks if lang == "bash")
    assert "curl --fail-with-body https://openrouter.ai/api/v1/chat/completions" in cmd
    assert 'Authorization: Bearer $OPENROUTER_API_KEY' in cmd
    assert "X-Api-Key" not in cmd and "X-Secret-Key" not in cmd
    request = json.loads(re.search(r"-d '(.*?)'", cmd, re.S).group(1))
    assert request["model"] == "openai/gpt-4o-mini"
    assert request["max_tokens"] == 16
    assert request["messages"] == [{"role": "user", "content": "What is the capital of France?"}]
    assert request["user"] == "demo-user"
    assert request["session_id"] == "capital-demo"
    assert request["trace"]["environment"] == "demo"
    assert "Set it as `OPENROUTER_API_KEY`" in page


def test_privacy_and_shared_account_boundaries(page):
    for text in ("credential-sharing policy", "custom metadata and model parameters",
                 "caller-supplied `stop` sequences", "no additional redaction layer",
                 "not a general-purpose scrubber", "bypasses those filters",
                 "`FI_CAPTURE_CONTENT` setting has no effect", "coordinate these settings with its owner",
                 "excluded keys take precedence", "provider error text"):
        assert text in page


def test_connection_test_is_not_end_to_end_proof(page):
    assert "connection test alone does not demonstrate" in page
    assert "sampling rate of **1.0**" in page
    assert "select `my-openrouter`" in page
    assert "HTTP 400 `no project_name`" in page
    assert "HTTP 401" in page and "HTTP 413" in page


def test_hierarchy_and_content_follow_current_provider_docs(page):
    assert "Generation spans and optional grouping spans" in page
    for name in ("trace_name", "span_name", "generation_name", "span.input", "span.output"):
        assert f"`{name}`" in page
    assert "sends the prompt twice" not in page
    assert "root is an LLM span" not in page
    assert "Cost is 0" not in page


def test_no_internal_diary_or_secrets(page):
    for forbidden in ("Live vendor verification", "not run live", "Beta.", "2026-10-19", "/Volumes/", "#3590"):
        assert forbidden not in page
    assert not re.search(r"[0-9a-f]{24,}|sk-or-v1-", page)
    assert "YOUR_API_KEY" in page and "YOUR_SECRET_KEY" in page
    assert page.rstrip().split("\n## ")[-1].startswith("Next steps")


def test_internal_links_point_at_existing_pages(page):
    for href in set(re.findall(r"\]\((/docs/[^)#]+)", page)):
        rel = href[len("/docs/"):]
        candidates = [os.path.join(REPO, "src", "pages", "docs", rel + ".mdx"),
                      os.path.join(REPO, "src", "pages", "docs", rel, "index.mdx")]
        assert any(os.path.exists(c) for c in candidates), href
    assert "](/docs/admin-settings/api-keys)" in page
