"""Static checks on the two files the page tells customers to use. Needs only PyYAML."""
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent.parent
GW = yaml.safe_load((HERE / "gravitee-opentelemetry.yml").read_text())["services"]["opentelemetry"]
COL = yaml.safe_load((HERE / "otelcol.yaml").read_text())


def test_gateway_exporter_speaks_what_the_collector_accepts():
    assert GW["enabled"] is True
    exp = GW["exporter"]
    assert exp["protocol"] == "http/protobuf"          # grpc is Gravitee's default; "http" would be OTLP/JSON
    assert exp["compression"] == "none"                # what was tested, and Gravitee's default
    # Gravitee appends /v1/traces itself; a URL that already ends in it is posted to /v1/traces/v1/traces
    assert not exp["endpoint"].rstrip("/").endswith("/v1/traces")


def test_gateway_content_is_off_by_default():
    assert GW["verbose"] is False                      # no span events with headers / context attributes
    rules = {r["attributeNamePattern"]: r for r in GW["redactionRules"]}
    for must in ("hostname", "ip", "http.target", "http.url", "url.query", "original-url", "client.address",
                 "user-id", "exception.message", "exception.stacktrace", "authorization", "cookie",
                 "x-gravitee-api-key", "x-api-key", "x-secret-key"):
        assert must in rules, must
        assert rules[must]["maskingStrategy"]["type"] == "FULL"
    # URL rules fire only when there is a query string, so plain paths stay readable
    for k in ("http.target", "http.url", "original-url"):
        assert rules[k]["valuePattern"] == "\\?"


def test_gateway_file_holds_no_secret_and_no_project_name():
    exp = GW["exporter"]
    assert "headers" not in exp                        # header values come from environment variables only
    # extraAttributes cannot carry project_name: Gravitee rewrites "_" to "." in the key
    assert not any("_" in k for a in GW.get("extraAttributes", []) for k in a)


def test_collector_sets_project_and_forwards_plain_protobuf():
    exp = COL["exporters"]["otlp_http/future_agi"]
    assert exp["compression"] == "none"
    assert exp["encoding"] == "proto"
    assert exp["headers"] == {"X-Api-Key": "${env:FI_API_KEY}", "X-Secret-Key": "${env:FI_SECRET_KEY}"}
    attrs = {a["key"]: a for a in COL["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"]["action"] == "upsert"
    assert attrs["project_name"]["value"] == "${env:FI_PROJECT_NAME}"
    assert attrs["project_type"]["value"] == "observe"


def test_collector_is_traces_only_and_quiet():
    svc = COL["service"]
    assert svc["telemetry"]["metrics"]["level"] == "none"
    assert set(svc["pipelines"]) == {"traces"}
    assert svc["pipelines"]["traces"]["processors"][0] == "resource/future_agi"
    assert COL["receivers"]["otlp"]["protocols"]["http"]["auth"]["authenticator"] == "bearertokenauth/gateway"
    assert "grpc" not in COL["receivers"]["otlp"]["protocols"]
