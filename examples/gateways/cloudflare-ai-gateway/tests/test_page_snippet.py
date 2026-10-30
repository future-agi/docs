"""The docs page and the files in this directory must say the same thing."""
import json
import os
import re

import pytest
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PAGE = os.path.join(REPO, "src", "pages", "docs", "integrations", "gateways", "cloudflare-ai-gateway.mdx")


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
    m = re.match(r'---\ntitle: "([^"]+)"\ndescription: "([^"]+)"\n---\n\n\[Cloudflare AI Gateway\]', page)
    assert m, "frontmatter, a blank line, then a task-oriented introduction"
    assert 120 <= len(m.group(2)) <= 160, len(m.group(2))


def test_style_rules(page):
    assert "—" not in page and "–" not in page, "no em or en dashes"
    assert page.rstrip().split("\n## ")[-1].startswith("Related guides")
    assert not re.search(r"\b(powerful|seamless|cutting-edge|game-changer)\b", page, re.I)


def test_the_yaml_on_the_page_is_otelcol_yaml(blocks):
    on_page = yaml.safe_load(block(blocks, "yaml", "bearertokenauth/gateway"))
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        assert on_page == yaml.safe_load(f)


def test_docker_command_matches_the_config(blocks):
    cmd = block(blocks, "bash", "docker run")
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        text = f.read()
    for name in set(re.findall(r"\$\{env:([A-Z_]+)", text)) - {"FI_CAPTURE_CONTENT"}:
        assert re.search(rf"-e {name}\b", cmd), name
    assert "otel/opentelemetry-collector-contrib:0.162.0" in cmd
    assert "--memory" in cmd and "-p 4318:4318" in cmd and "/etc/otelcol/config.yaml" in cmd
    assert "FI_CAPTURE_CONTENT" not in cmd, "content stays off unless the reader opts in"


def test_every_environment_variable_is_explained(page):
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        names = set(re.findall(r"\$\{env:([A-Z_]+)", f.read()))
    for name in names:
        assert f"`{name}`" in page, name


def test_cloudflare_headers_carry_the_collector_token_and_never_the_future_agi_keys(page):
    row = re.search(r"\| Headers \| (.*?) \|\n", page).group(1)
    assert "`Authorization: Bearer YOUR_GATEWAY_TOKEN`" in row
    assert "X-Api-Key" not in row and "X-Secret-Key" not in row


def test_cloudflares_attribute_names_are_used_unchanged(page):
    real = ("cf.aig.request", "gen_ai.request.model", "gen_ai.provider.name", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
            "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.usage.cost")
    documented = ("gen_ai.model.provider", "gen_ai.prompt_json", "gen_ai.completion_json")
    for name in real + documented + ("cf-aig-metadata", "cf-aig-otel-trace-id", "cf-aig-otel-parent-span-id"):
        assert f"`{name}`" in page, name


def test_the_page_names_match_the_captured_payload(page):
    with open(os.path.join(HERE, "tests", "fixtures", "cloudflare-2026-10-18-chat.json")) as f:
        body = json.load(f)
    rs = body["resourceSpans"][0]
    span = rs["scopeSpans"][0]["spans"][0]
    assert f"named `{span['name']}`" in page and f"scope `{rs['scopeSpans'][0]['scope']['name']}`" in page
    for a in span["attributes"]:
        if a["key"].startswith("gen_ai."):
            assert f"`{a['key']}`" in page, a["key"]


def test_cloud_run_command_provides_everything_the_config_reads(blocks):
    cmd = block(blocks, "bash", "gcloud run deploy")
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        names = set(re.findall(r"\$\{env:([A-Z_]+)", f.read())) - {"FI_CAPTURE_CONTENT"}
    secrets = re.search(r"--set-secrets=(\S+)", cmd).group(1).split(",")
    env = re.search(r"--set-env-vars=(\S+)", cmd).group(1).split(",")
    provided = {s.split("=")[0] for s in secrets + env}
    assert names <= provided, names - provided
    for secret_var in ("GATEWAY_TOKEN", "FI_API_KEY", "FI_SECRET_KEY"):
        assert secret_var not in {e.split("=")[0] for e in env}, "keys come from Secret Manager, not plain env"
    mount = next(s.split("=")[0] for s in secrets if s.startswith("/"))
    assert f"--args=--config={mount}" in cmd
    assert "--port 4318" in cmd and "docker.io/otel/opentelemetry-collector-contrib:0.162.0" in cmd
    assert "FI_CAPTURE_CONTENT" not in cmd


def test_api_example_sets_the_same_exporter_fields(blocks):
    cmd = block(blocks, "bash", "ai-gateway/gateways")
    data = json.loads(re.search(r"--data '(.*?)'", cmd, flags=re.S).group(1))
    (otel,) = data["otel"]
    assert otel["url"].endswith("/v1/traces") and otel["content_type"] in ("json", "protobuf")
    assert otel["headers"] == {"Authorization": "Bearer YOUR_GATEWAY_TOKEN"}


def test_the_removed_keys_the_page_lists_are_removed_by_the_config(page):
    with open(os.path.join(HERE, "otelcol.yaml")) as f:
        cfg = yaml.safe_load(f)
    statements = [s for b in cfg["processors"]["transform/cloudflare"]["trace_statements"] for s in b["statements"]]
    regexes = []
    for s in statements:
        m = re.search(r'delete_matching_keys\(attributes, "((?:[^"\\]|\\.)*)"\)', s)
        if m:
            regexes.append(re.compile(json.loads(f'"{m.group(1)}"')))
    deleted = {m.group(1) for s in statements for m in [re.match(r'delete_key\(attributes, "([^"]+)"\)', s)] if m}
    section = page.split("With the collector default")[1].split("Kept:")[0]
    for key in re.findall(r"`((?:gen_ai|exception)\.[a-z_.]+)`", section):
        assert key in deleted or any(r.search(key) for r in regexes), key


def test_the_curl_example_uses_valid_hex_ids(page):
    tid = re.search(r"cf-aig-otel-trace-id: ([^']+)'", page).group(1)
    sid = re.search(r"cf-aig-otel-parent-span-id: ([^']+)'", page).group(1)
    assert re.fullmatch(r"[0-9a-f]{32}", tid) and re.fullmatch(r"[0-9a-f]{16}", sid)


def test_no_secret_looking_value_on_the_page(page):
    without_ids = page.replace("0123456789abcdef0123456789abcdef", "").replace("0123456789abcdef", "")   # the trace-id example
    assert not re.search(r"[0-9a-f]{24,}", without_ids)
    assert "YOUR_API_KEY" in page and "YOUR_SECRET_KEY" in page


def test_internal_links_point_at_pages_that_exist(page):
    for href in set(re.findall(r"\]\((/docs/[^)#]+)", page)):
        rel = href[len("/docs/"):]
        candidates = [os.path.join(REPO, "src", "pages", "docs", rel + ".mdx"), os.path.join(REPO, "src", "pages", "docs", rel, "index.mdx")]
        assert any(os.path.exists(c) for c in candidates), href


def test_page_focuses_on_setup_and_content_safety(page):
    assert "## Live vendor verification" not in page
    assert "Scope of the live run" not in page
    assert "<Step title=\"Add the exporter in Cloudflare\">" in page
    assert "The collector filters them before export to Observe by default" in page
    assert "Do not put your Future AGI keys here" in page
    assert "Nobody ran Cloudflare" not in page and "STANDIN" not in page
