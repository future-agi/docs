"""Invariants of the OpenTelemetry Collector recipe. `run_e2e.sh collector` runs it for real."""
import os
import re

import pytest
import yaml

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "native", "otelcol.yaml")


@pytest.fixture(scope="module")
def cfg():
    with open(PATH) as f:
        return yaml.safe_load(f)


def test_collector_telemetry_metrics_are_off(cfg):
    assert cfg["service"]["telemetry"]["metrics"]["level"] == "none"


def test_exporter_is_uncompressed_proto_with_both_key_headers(cfg):
    exp = cfg["exporters"]["otlp_http/future_agi"]
    assert exp["compression"] == "none"
    assert exp["encoding"] == "proto"
    assert set(exp["headers"]) == {"X-Api-Key", "X-Secret-Key"}
    assert exp["traces_endpoint"] == "${env:FI_TRACES_URL}"


def test_no_literal_secrets_in_the_file():
    text = open(PATH).read()
    assert not re.search(r"(sk-|ak-)[A-Za-z0-9]{8,}", text)
    for value in re.findall(r"X-(?:Api|Secret)-Key:\s*(\S+)", text):
        assert value.startswith("${env:")


def test_traces_pipeline_only(cfg):
    pipelines = cfg["service"]["pipelines"]
    assert list(pipelines) == ["traces"]
    assert pipelines["traces"]["receivers"] == ["otlp"]
    assert pipelines["traces"]["processors"] == ["resource/future_agi", "transform/privacy", "batch"]
    assert pipelines["traces"]["exporters"] == ["otlp_http/future_agi"]


def test_project_is_named_by_the_collector_without_overriding_the_gateway(cfg):
    attrs = {a["key"]: a for a in cfg["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"]["value"] == "${env:FI_PROJECT_NAME}" and attrs["project_name"]["action"] == "insert"
    assert attrs["project_type"]["value"] == "observe"


def test_privacy_processor_covers_content_identity_and_error_text(cfg):
    stmts = [s for block in cfg["processors"]["transform/privacy"]["trace_statements"] for s in block["statements"]]
    deleted = {m.group(1) for s in stmts if (m := re.match(r'delete_key\(attributes, "([^"]+)"\)', s))}
    assert {
        "tfy.input", "tfy.output", "tfy.input_short_hand",
        "gen_ai.input.messages", "gen_ai.output.messages",
        "tfy.request.metadata", "tfy.prompt_variables", "tfy.error_message",
        "tfy.request.created_by_subject", "tfy.request.identity",
        "tfy.request.created_by_subject_pat_name", "client.address", "exception.message", "exception.stacktrace",
    } <= deleted
    assert any(s.startswith("set(status.message") for s in stmts)


def test_receivers_accept_http_and_grpc(cfg):
    assert set(cfg["receivers"]["otlp"]["protocols"]) == {"http", "grpc"}


def test_the_yaml_on_the_page_is_the_yaml_in_the_repo():
    page = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "src", "pages", "docs",
        "integrations", "gateways", "truefoundry.mdx",
    )
    if not os.path.exists(page):
        pytest.skip("docs page not in this checkout")
    text = open(page).read()
    block = re.search(r"```yaml\n(.*?)\n```", text, re.S).group(1)
    assert yaml.safe_load(block) == yaml.safe_load(open(PATH))
