"""otelcol.yaml: what the recipe promises, checked without starting a collector."""
import json
import os
import re

import pytest
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(HERE, "otelcol.yaml")


@pytest.fixture(scope="module")
def cfg():
    with open(PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def text():
    with open(PATH) as f:
        return f.read()


def statements(cfg, context):
    out = []
    for block in cfg["processors"]["transform/cloudflare"]["trace_statements"]:
        if block["context"] == context:
            out += block["statements"]
    return out


def ottl_regex(stmt):
    literal = re.search(r'delete_matching_keys\(attributes, "((?:[^"\\]|\\.)*)"\)', stmt).group(1)
    return re.compile(json.loads(f'"{literal}"'))


def test_metrics_level_none_and_no_compression(cfg):
    assert cfg["service"]["telemetry"]["metrics"]["level"] == "none"
    exp = cfg["exporters"]["otlp_http/future_agi"]
    assert exp["compression"] == "none" and exp["encoding"] in ("proto", "json")


def test_traces_only_pipeline_in_the_documented_order(cfg):
    pipelines = cfg["service"]["pipelines"]
    assert list(pipelines) == ["traces"]
    t = pipelines["traces"]
    assert t["receivers"] == ["otlp"] and t["exporters"] == ["otlp_http/future_agi"]
    assert t["processors"] == ["resource/future_agi", "transform/cloudflare", "batch"]


def test_receiver_is_http_only_and_requires_the_bearer_token(cfg):
    protocols = cfg["receivers"]["otlp"]["protocols"]
    assert list(protocols) == ["http"]
    assert protocols["http"]["auth"]["authenticator"] == "bearertokenauth/gateway"
    ext = cfg["extensions"]["bearertokenauth/gateway"]
    assert ext["scheme"] == "Bearer" and ext["token"] == "${env:GATEWAY_TOKEN}"
    assert cfg["service"]["extensions"] == ["bearertokenauth/gateway"]


def test_future_agi_keys_come_from_the_environment_only(cfg, text):
    headers = cfg["exporters"]["otlp_http/future_agi"]["headers"]
    assert headers == {"X-Api-Key": "${env:FI_API_KEY}", "X-Secret-Key": "${env:FI_SECRET_KEY}"}
    assert not re.search(r"[0-9a-f]{24,}", text)


def test_project_is_named_by_the_collector(cfg):
    attrs = {a["key"]: a for a in cfg["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"]["value"] == "${env:FI_PROJECT_NAME}" and attrs["project_name"]["action"] == "upsert"
    assert attrs["project_type"]["value"] == "observe"


def test_content_switch_defaults_to_off_everywhere(text):
    uses = re.findall(r"\$\{env:FI_CAPTURE_CONTENT[^}]*\}", text)
    assert uses and all(u == "${env:FI_CAPTURE_CONTENT:-false}" for u in uses)


@pytest.mark.parametrize("src,dst", [
    ("gen_ai.input.messages", "input.value"), ("gen_ai.output.messages", "output.value"),   # what the real gateway sends
    ("gen_ai.prompt_json", "input.value"), ("gen_ai.completion_json", "output.value"),      # the names on Cloudflare's page
])
def test_cloudflares_prompt_and_completion_are_always_removed_after_the_optional_copy(cfg, src, dst):
    span = statements(cfg, "span")
    copy = next(i for i, s in enumerate(span) if s.startswith(f'set(attributes["{dst}"], attributes["{src}"])'))
    delete = span.index(f'delete_key(attributes, "{src}")')
    assert copy < delete
    assert '== "true"' in span[copy]


def test_input_and_output_are_marked_json_only_with_the_opt_in(cfg):
    span = statements(cfg, "span")
    for side in ("input", "output"):
        s = next(s for s in span if s.startswith(f'set(attributes["{side}.mime_type"]'))
        assert '"application/json"' in s and '== "true"' in s


def test_other_content_spellings_are_removed_only_when_not_opted_in(cfg):
    regexes = [ottl_regex(s) for s in statements(cfg, "span") if s.startswith("delete_matching_keys")]
    for key in ("gen_ai.prompt", "gen_ai.completion", "gen_ai.prompt.0.content", "gen_ai.completion.0.content",
                "gen_ai.input.messages", "gen_ai.output.messages"):
        assert any(r.search(key) for r in regexes), key
    for key in ("gen_ai.request.model", "gen_ai.model.provider", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
                "gen_ai.usage.cost", "gen_ai.cost.total", "gen_ai.provider.name", "input.value", "output.value", "team", "user_id"):
        assert not any(r.search(key) for r in regexes), key
    for s in statements(cfg, "span"):
        if s.startswith("delete_matching_keys"):
            assert '"${env:FI_CAPTURE_CONTENT:-false}" != "true"' in s


def test_error_text_and_exception_details_are_removed_unless_opted_in(cfg):
    assert any(s.startswith('set(status.message, "error")') and '!= "true"' in s for s in statements(cfg, "span"))
    ev = statements(cfg, "spanevent")
    assert {re.search(r'"([a-z.]+)"', s).group(1) for s in ev} == {"exception.message", "exception.stacktrace"}
    assert all('!= "true"' in s for s in ev)


def test_cloudflare_names_are_mapped_for_observe_and_the_originals_kept(cfg):
    span = statements(cfg, "span")
    # the real gateway sends gen_ai.provider.name itself; the copy covers the name on Cloudflare's page
    assert any(s.startswith('set(attributes["gen_ai.provider.name"], attributes["gen_ai.model.provider"])') for s in span)
    assert any(s.startswith('set(attributes["gen_ai.cost.total"], attributes["gen_ai.usage.cost"])') for s in span)
    assert not any(re.match(r'delete_key\(attributes, "gen_ai\.(model\.provider|usage\.cost)"\)', s) for s in span)
    assert any('"LLM"' in s and 'gen_ai.request.model"] != nil' in s for s in span)
    assert any('"CHAIN"' in s and 'gen_ai.request.model"] == nil' in s for s in span)


def test_env_variables_the_file_reads_are_the_documented_ones(text):
    assert set(re.findall(r"\$\{env:([A-Z_]+)", text)) == {"GATEWAY_TOKEN", "FI_API_KEY", "FI_SECRET_KEY", "FI_PROJECT_NAME", "FI_TRACES_URL", "FI_CAPTURE_CONTENT"}


def test_batches_stay_small(cfg):
    b = cfg["processors"]["batch"]
    assert b["send_batch_max_size"] <= 512 and b["send_batch_size"] <= b["send_batch_max_size"]
