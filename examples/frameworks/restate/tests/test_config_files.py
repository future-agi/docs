"""The shipped collector and server configs say what the page says."""
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import yaml

EXAMPLE = Path(__file__).resolve().parent.parent
COL = yaml.safe_load((EXAMPLE / "otelcol.yaml").read_text())
SERVER = tomllib.loads((EXAMPLE / "restate.toml").read_text())


def _statements(processor: str) -> list[str]:
    return [s for group in COL["processors"][processor]["trace_statements"] for s in group["statements"]]


def test_collector_sends_uncompressed_otlp_http_and_no_self_metrics():
    exporter = COL["exporters"]["otlp_http/future_agi"]
    assert exporter["compression"] == "none"
    assert exporter["encoding"] == "proto"
    assert exporter["traces_endpoint"] == "${env:FI_TRACES_URL}"
    assert COL["service"]["telemetry"]["metrics"]["level"] == "none"


def test_collector_passes_both_key_headers_through_and_holds_no_keys():
    http = COL["receivers"]["otlp"]["protocols"]["http"]
    assert http["include_metadata"] is True
    assert http["traces_url_path"] == "/tracer/v1/traces"
    setter = {h["key"]: h for h in COL["extensions"]["headers_setter"]["headers"]}
    assert set(setter) == {"X-Api-Key", "X-Secret-Key"}
    assert all(h["from_context"] == k and h["action"] == "upsert" for k, h in setter.items())
    assert COL["exporters"]["otlp_http/future_agi"]["auth"]["authenticator"] == "headers_setter"
    assert "headers_setter" in COL["service"]["extensions"]
    text = (EXAMPLE / "otelcol.yaml").read_text()
    assert "FI_API_KEY" not in text and "FI_SECRET_KEY" not in text


def test_collector_stamps_project_without_overwriting_one_the_sender_set():
    attrs = {a["key"]: a for a in COL["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"] == {"key": "project_name", "value": "${env:FI_PROJECT_NAME}", "action": "insert"}
    assert attrs["project_type"]["value"] == "observe" and attrs["project_type"]["action"] == "insert"


def test_host_names_addresses_and_stack_traces_are_always_removed():
    always = _statements("transform/always")
    for key in ("service.instance.id", "host.name", "restate.deployment.address", "client.socket.address",
                "client.socket.port", "exception.stacktrace"):
        assert f'delete_key(attributes, "{key}")' in always
    groups = COL["processors"]["transform/always"]["trace_statements"]
    assert all("conditions" not in g for g in groups)


def test_error_text_and_object_keys_are_removed_unless_opted_in():
    groups = COL["processors"]["transform/details"]["trace_statements"]
    assert all(g["conditions"] == ['"${env:KEEP_RESTATE_DETAILS:-false}" != "true"'] for g in groups)
    details = _statements("transform/details")
    assert 'delete_key(attributes, "error.message")' in details
    assert 'set(status.message, "error") where status.message != ""' in details
    assert 'delete_key(attributes, "exception.message")' in details
    assert any(s.startswith('replace_pattern(attributes["restate.invocation.target"]') for s in details)


def test_pipeline_order():
    pipe = COL["service"]["pipelines"]["traces"]
    assert pipe == {
        "receivers": ["otlp"],
        "processors": ["resource/future_agi", "transform/always", "transform/details"],
        "exporters": ["otlp_http/future_agi"],
    }


def test_server_config_targets_the_collector_with_both_headers():
    assert SERVER["tracing-endpoint"] == "otlp+http://localhost:4318/tracer/v1/traces"
    assert set(SERVER["tracing-headers"]) == {"X-Api-Key", "X-Secret-Key"}
    assert all(v.startswith("<") for v in SERVER["tracing-headers"].values())  # placeholders, no real keys
