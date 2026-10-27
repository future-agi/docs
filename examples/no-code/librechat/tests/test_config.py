"""Static checks of the files a customer copies: collector config, env block, Compose override, docs page."""
import pathlib
import re

import yaml

HERE = pathlib.Path(__file__).resolve().parent.parent
DOCS_ROOT = HERE.parents[2]
PAGE = DOCS_ROOT / "src" / "pages" / "docs" / "integrations" / "no-code" / "librechat.mdx"
OTELCOL = yaml.safe_load((HERE / "otelcol" / "otelcol.yaml").read_text())
ENV_TEXT = (HERE / "env" / "futureagi.env.example").read_text()
ENV = dict(line.split("=", 1) for line in ENV_TEXT.splitlines() if line and not line.startswith("#"))


def test_collector_has_no_self_metrics_and_no_compression():
    assert OTELCOL["service"]["telemetry"]["metrics"]["level"] == "none"
    for name, exporter in OTELCOL["exporters"].items():
        assert exporter["compression"] == "none", name
        assert exporter["traces_endpoint"] == "${env:FI_TRACES_URL}"


def test_collector_stores_no_credentials():
    text = (HERE / "otelcol" / "otelcol.yaml").read_text()
    for exporter in OTELCOL["exporters"].values():
        assert "headers" not in exporter  # credentials only come from the caller, via headers_setter
    assert "FI_API_KEY" not in text and "FI_SECRET_KEY" not in text


def test_collector_receivers_match_librechat_exporters():
    lf = OTELCOL["receivers"]["otlp/langfuse"]["protocols"]["http"]
    assert lf["endpoint"].endswith(":4319")
    assert lf["traces_url_path"] == "/api/public/otel/v1/traces"  # @langfuse/otel appends this to LANGFUSE_BASE_URL
    be = OTELCOL["receivers"]["otlp/backend"]["protocols"]["http"]
    assert be["endpoint"].endswith(":4318")
    for receiver in OTELCOL["receivers"].values():
        assert receiver["protocols"]["http"]["include_metadata"] is True


def test_content_capture_defaults_off():
    statements = " ".join(OTELCOL["processors"]["transform/langfuse"]["trace_statements"][0]["statements"])
    assert '"${env:FI_CAPTURE_CONTENT:-false}" != "true"' in statements
    assert 'delete_matching_keys(attributes, "^langfuse\\\\.(observation|trace)\\\\.(input|output|status_message)$")' in statements
    # input.value / output.value are only set when capture is explicitly true
    for stmt in OTELCOL["processors"]["transform/langfuse"]["trace_statements"][0]["statements"]:
        if 'attributes["input.value"]' in stmt or 'attributes["output.value"]' in stmt:
            assert '== "true"' in stmt


def test_resource_safety_net_and_project():
    attrs = OTELCOL["processors"]["resource/future_agi"]["attributes"]
    assert {"key": "project_name", "value": "${env:FI_PROJECT_NAME}", "action": "upsert"} in attrs
    assert any(a.get("pattern") == r"^(host|os|process|container)\..*" and a["action"] == "delete" for a in attrs)


def test_pipelines():
    pipes = OTELCOL["service"]["pipelines"]
    assert pipes["traces/langfuse"]["receivers"] == ["otlp/langfuse"]
    assert pipes["traces/backend"]["receivers"] == ["otlp/backend"]
    assert "transform/langfuse" in pipes["traces/langfuse"]["processors"]
    assert "transform/backend" in pipes["traces/backend"]["processors"]
    assert pipes["traces/backend"]["processors"][0] == "filter/background"
    assert OTELCOL["processors"]["filter/background"]["traces"]["span"] == [
        'IsMatch(name, "^mongoose\\\\.") and IsRootSpan()']


def test_env_block_points_both_exports_at_the_collector():
    assert ENV["LANGFUSE_BASE_URL"] == "http://futureagi-otelcol:4319"
    assert ENV["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] == "http://futureagi-otelcol:4318/v1/traces"
    assert ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"
    assert ENV["OTEL_TRACING_ENABLED"] == "true"
    assert ENV["OTEL_EXPORTER_OTLP_HEADERS"] == "X-Api-Key=YOUR_FUTURE_AGI_API_KEY,X-Secret-Key=YOUR_FUTURE_AGI_SECRET_KEY"
    assert ENV["LANGFUSE_PUBLIC_KEY"] == "YOUR_FUTURE_AGI_API_KEY"
    assert ENV["LANGFUSE_SECRET_KEY"] == "YOUR_FUTURE_AGI_SECRET_KEY"


def test_env_block_keeps_host_details_and_extra_signals_off():
    assert ENV["OTEL_NODE_RESOURCE_DETECTORS"] == "env"
    assert ENV["OTEL_METRICS_EXPORTER"] == "none"
    assert ENV["OTEL_LOGS_EXPORTER"] == "none"
    assert "OTEL_LOGS_ENABLED" not in ENV  # Future AGI takes traces only


def test_compose_override_matches_collector():
    override = yaml.safe_load((HERE / "docker-compose.override.yml.example").read_text())
    svc = override["services"]["futureagi-otelcol"]
    assert "ports" not in svc  # never published
    env = dict(e.split("=", 1) for e in svc["environment"])
    assert env["FI_CAPTURE_CONTENT"] == "false"
    assert env["FI_TRACES_URL"] == "https://api.futureagi.com/tracer/v1/traces"
    assert svc["image"].endswith(":0.162.0")
    assert "futureagi-otelcol" in override["services"]["api"]["depends_on"]


def _page_blocks():
    return [b.strip() for b in re.findall(r"```(?:bash|yaml|dotenv)\n(.*?)```", PAGE.read_text(), re.S)]


def test_page_env_block_is_the_shipped_file():
    assert ENV_TEXT.strip() in _page_blocks()


def test_page_collector_block_is_the_shipped_file():
    assert (HERE / "otelcol" / "otelcol.yaml").read_text().strip() in _page_blocks()


def test_page_compose_block_is_the_shipped_file():
    assert (HERE / "docker-compose.override.yml.example").read_text().strip() in _page_blocks()


def test_custom_endpoint_requests_provider_reported_streamed_usage():
    config = yaml.safe_load((HERE / "librechat.yaml").read_text())
    endpoint = config["endpoints"]["custom"][0]
    assert endpoint["addParams"]["streamUsage"] is True
    assert endpoint["baseURL"] == "${TEST_LLM_BASE_URL}"
    assert endpoint["apiKey"] == "${TEST_LLM_API_KEY}"


def test_page_documents_the_streamed_usage_requirement():
    page = PAGE.read_text()
    assert "addParams:\n  streamUsage: true" in page
    assert "stream_options.include_usage" in page
    assert "missing usage is unknown, not zero usage" in page
