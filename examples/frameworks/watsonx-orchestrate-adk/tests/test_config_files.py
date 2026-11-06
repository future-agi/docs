"""The shipped collector config says what the page says."""
from pathlib import Path

import yaml

EXAMPLE = Path(__file__).resolve().parent.parent
TEXT = (EXAMPLE / "otelcol.yaml").read_text()
COL = yaml.safe_load(TEXT)


def _groups(processor: str) -> list[dict]:
    return COL["processors"][processor]["trace_statements"]


def _statements(processor: str) -> list[str]:
    return [s for group in _groups(processor) for s in group["statements"]]


def test_collector_sends_uncompressed_otlp_http_with_both_keys_and_no_self_metrics():
    exporter = COL["exporters"]["otlp_http/future_agi"]
    assert exporter["compression"] == "none"
    assert exporter["encoding"] == "proto"
    assert exporter["traces_endpoint"] == "${env:FI_TRACES_URL}"
    assert exporter["headers"] == {"X-Api-Key": "${env:FI_API_KEY}", "X-Secret-Key": "${env:FI_SECRET_KEY}"}
    assert COL["service"]["telemetry"]["metrics"]["level"] == "none"


def test_incoming_headers_are_never_forwarded():
    # No include_metadata and no headers_setter: an Authorization bearer that reaches the
    # receiver has no path to the exporter.
    http = COL["receivers"]["otlp"]["protocols"]["http"]
    assert "include_metadata" not in http
    assert "extensions" not in COL and "extensions" not in COL["service"]
    assert "auth" not in COL["exporters"]["otlp_http/future_agi"]
    assert "Authorization" not in yaml.safe_dump(COL["exporters"])


def test_receiver_uses_the_default_otlp_path_the_sdk_posts_to():
    http = COL["receivers"]["otlp"]["protocols"]["http"]
    assert http == {"endpoint": "0.0.0.0:4318"}  # WXO_OTLP_ENDPOINT=http://<host>:4318/v1/traces


def test_collector_stamps_project_without_overwriting_one_the_app_set():
    attrs = {a["key"]: a for a in COL["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"] == {"key": "project_name", "value": "${env:FI_PROJECT_NAME}", "action": "insert"}
    assert attrs["project_type"] == {"key": "project_type", "value": "observe", "action": "insert"}


def test_sdk_span_kinds_provider_session_and_placeholder_user_are_mapped():
    mapping = _statements("transform/map")
    for sdk, fi in (("llm", "LLM"), ("tool", "TOOL"), ("agent", "AGENT")):
        assert f'set(attributes["fi.span.kind"], "{fi}") where attributes["span.kind"] == "{sdk}" and attributes["fi.span.kind"] == nil' in mapping
    assert any('"CHAIN"' in s and '"root"' in s and '"general"' in s for s in mapping)
    assert any(s.startswith('set(attributes["gen_ai.provider.name"], attributes["llm.provider"])') for s in mapping)
    assert any(s.startswith('set(attributes["session.id"], attributes["conversation.id"])') for s in mapping)
    assert 'delete_key(attributes, "user.id") where attributes["user.id"] == "Unknown User"' in mapping
    assert all("conditions" not in g for g in _groups("transform/map"))


def test_stack_traces_host_and_process_details_are_always_removed():
    always = _statements("transform/always")
    assert 'delete_key(attributes, "exception.stacktrace")' in always
    assert 'delete_matching_keys(attributes, "^(host|process)\\\\.")' in always
    assert all("conditions" not in g for g in _groups("transform/always"))


def test_content_error_text_and_user_ids_are_removed_unless_opted_in():
    groups = _groups("transform/content")
    assert all(g["conditions"] == ['"${env:KEEP_WXO_CONTENT:-false}" != "true"'] for g in groups)
    content = _statements("transform/content")
    for key in ("input.value", "output.value", "tool.input", "tool.output", "agent.input", "agent.output", "user.id",
                "exception.message"):
        assert f'delete_key(attributes, "{key}")' in content
    assert 'set(status.message, "error") where status.message != ""' in content


def test_pipeline_order():
    assert COL["service"]["pipelines"]["traces"] == {
        "receivers": ["otlp"],
        "processors": ["resource/future_agi", "transform/map", "transform/always", "transform/content"],
        "exporters": ["otlp_http/future_agi"],
    }


def test_no_secrets_or_local_details_in_the_config():
    for needle in ("sk-", "localhost:14338", "/Users/", "th8103"):
        assert needle not in TEXT
