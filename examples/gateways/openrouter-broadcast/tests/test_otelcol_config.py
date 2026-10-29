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
    for block in cfg["processors"]["transform/openrouter"]["trace_statements"]:
        if block["context"] == context:
            out += block["statements"]
    return out


def ottl_regex(stmt):
    """The regex of a delete_matching_keys(attributes, "...") statement, as OTTL reads the string literal."""
    literal = re.search(r'delete_matching_keys\(attributes, "((?:[^"\\]|\\.)*)"\)', stmt).group(1)
    return re.compile(json.loads(f'"{literal}"'))


def test_metrics_level_none_and_no_compression(cfg):
    assert cfg["service"]["telemetry"]["metrics"]["level"] == "none"
    exp = cfg["exporters"]["otlp_http/future_agi"]
    assert exp["compression"] == "none"
    assert exp["encoding"] in ("proto", "json")


def test_traces_only_pipeline_in_the_documented_order(cfg):
    pipelines = cfg["service"]["pipelines"]
    assert list(pipelines) == ["traces"]
    t = pipelines["traces"]
    assert t["receivers"] == ["otlp"] and t["exporters"] == ["otlp_http/future_agi"]
    assert t["processors"] == ["resource/future_agi", "transform/openrouter", "batch"]


def test_receiver_is_http_only_and_requires_the_bearer_token(cfg):
    protocols = cfg["receivers"]["otlp"]["protocols"]
    assert list(protocols) == ["http"]              # Broadcast speaks OTLP/HTTP; nothing else is opened
    http = protocols["http"]
    assert http["auth"]["authenticator"] == "bearertokenauth/broadcast"
    ext = cfg["extensions"]["bearertokenauth/broadcast"]
    assert ext["scheme"] == "Bearer" and ext["token"] == "${env:BROADCAST_TOKEN}"
    assert cfg["service"]["extensions"] == ["bearertokenauth/broadcast"]


def test_future_agi_keys_come_from_the_environment_only(cfg, text):
    headers = cfg["exporters"]["otlp_http/future_agi"]["headers"]
    assert headers == {"X-Api-Key": "${env:FI_API_KEY}", "X-Secret-Key": "${env:FI_SECRET_KEY}"}
    assert "Authorization" not in headers
    assert not re.search(r"[0-9a-f]{24,}", text), "a literal secret-looking value is in the file"


def test_project_is_named_by_the_collector(cfg):
    attrs = {a["key"]: a for a in cfg["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"]["value"] == "${env:FI_PROJECT_NAME}" and attrs["project_name"]["action"] == "upsert"
    assert attrs["project_type"]["value"] == "observe"


def test_content_switch_defaults_to_off_everywhere(text):
    uses = re.findall(r"\$\{env:FI_CAPTURE_CONTENT[^}]*\}", text)
    assert uses and all(u == "${env:FI_CAPTURE_CONTENT:-false}" for u in uses)


def test_every_content_removal_is_gated_by_the_switch(cfg):
    for ctx in ("span", "spanevent"):
        for s in statements(cfg, ctx):
            if s.startswith(("delete_key", "delete_matching_keys")) or "status.message" in s.split(" where ")[0]:
                if "input.value" in s:
                    continue
                assert '"${env:FI_CAPTURE_CONTENT:-false}"' in s, s


def test_content_keys_are_removed_by_the_off_rules(cfg):
    regexes = [ottl_regex(s) for s in statements(cfg, "span") if s.startswith("delete_matching_keys")]
    must_go = [
        "span.input", "span.output", "trace.input", "trace.output",                         # OpenTelemetry Collector page
        "gen_ai.prompt", "gen_ai.completion",                                               # same
        "span.input.truncated", "span.output.truncated",                                   # "<key>.truncated" companions
        "gen_ai.prompt.0.content", "gen_ai.completion.0.content",                          # indexed spelling
        "gen_ai.input.messages", "gen_ai.output.messages",                                 # OTel GenAI conventions
        "span.metadata.openrouter_generation.upstream_raw_response_usage",
        "trace.metadata.openrouter_generation.upstream_raw_response_usage",
        "span.status_message",                                                             # real payload, 2026-10-20: error text as an attribute
    ]
    for key in must_go:
        assert any(r.search(key) for r in regexes), key


def test_the_off_rules_leave_everything_else_alone(cfg):
    regexes = [ottl_regex(s) for s in statements(cfg, "span") if s.startswith("delete_matching_keys")]
    must_stay = [
        "gen_ai.request.model", "gen_ai.response.model", "gen_ai.response.id", "gen_ai.system", "gen_ai.operation.name",
        "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.usage.total_tokens", "gen_ai.response.finish_reason",
        "user.id", "session.id", "openrouter.inter_token_latency_ms", "trace.metadata.environment",
        "trace.metadata.input_channel", "trace.metadata.output_format",                    # custom metadata that merely contains the words
        "span.metadata.openrouter_generation.cache_write_tokens", "span.metadata.openrouter_generation.usage_is_estimated",
        "input.value", "output.value",
    ]
    for key in must_stay:
        assert not any(r.search(key) for r in regexes), key


def test_error_text_and_exception_details_are_removed_unless_opted_in(cfg):
    span = statements(cfg, "span")
    assert any(s.startswith('set(status.message, "error")') for s in span)
    ev = statements(cfg, "spanevent")
    assert {re.search(r'"([a-z.]+)"', s).group(1) for s in ev} == {"exception.message", "exception.stacktrace"}


def test_content_on_fills_the_input_and_output_panes_from_span_input_output(cfg):
    span = statements(cfg, "span")
    assert any(s.startswith('set(attributes["input.value"], attributes["span.input"])') and '== "true"' in s for s in span)
    assert any(s.startswith('set(attributes["output.value"], attributes["span.output"])') and '== "true"' in s for s in span)


def test_token_key_aliases_only_fill_gaps(cfg):
    span = statements(cfg, "span")
    for new, old in (("input", "prompt"), ("output", "completion")):
        s = [x for x in span if x.startswith(f'set(attributes["gen_ai.usage.{new}_tokens"]')][0]
        assert f'attributes["gen_ai.usage.{new}_tokens"] == nil' in s and f'attributes["gen_ai.usage.{old}_tokens"] != nil' in s


def test_span_kinds_are_set_from_the_presence_of_a_model(cfg):
    span = statements(cfg, "span")
    assert any('"LLM"' in s and 'gen_ai.request.model"] != nil' in s for s in span)
    assert any('"CHAIN"' in s and 'gen_ai.request.model"] == nil' in s for s in span)


def test_env_variables_the_file_reads_are_the_documented_ones(text):
    names = set(re.findall(r"\$\{env:([A-Z_]+)", text))
    assert names == {"BROADCAST_TOKEN", "FI_API_KEY", "FI_SECRET_KEY", "FI_PROJECT_NAME", "FI_TRACES_URL", "FI_CAPTURE_CONTENT"}


def test_batches_stay_small(cfg):
    b = cfg["processors"]["batch"]
    assert b["send_batch_max_size"] <= 512 and b["send_batch_size"] <= b["send_batch_max_size"]


def test_openrouter_cost_reaches_the_key_observe_reads(cfg):
    """Real Broadcast payload (2026-10-20, Cost metadata on): the cost is gen_ai.usage.total_cost."""
    span = statements(cfg, "span")
    assert any(
        s.startswith('set(attributes["gen_ai.cost.total"], attributes["gen_ai.usage.total_cost"])')
        and 'attributes["gen_ai.usage.total_cost"] != nil' in s
        for s in span
    )
