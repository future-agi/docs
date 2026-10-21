"""The shipped policy XML and collector config say what the page says they say."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "policy" / "otlp-egress.policy.xml"
COL = yaml.safe_load((ROOT / "otelcol.yaml").read_text())
COL_TEXT = (ROOT / "otelcol.yaml").read_text()


def inbound():
    return ET.parse(POLICY).getroot().find("inbound")


def test_policy_is_well_formed_and_sets_both_keys_from_named_values():
    headers = {h.get("name"): h for h in inbound().findall("set-header")}
    assert headers["X-Api-Key"].find("value").text == "{{fi-api-key}}"
    assert headers["X-Secret-Key"].find("value").text == "{{fi-secret-key}}"
    assert headers["X-Api-Key"].get("exists-action") == headers["X-Secret-Key"].get("exists-action") == "override"


def test_policy_drops_the_callers_credentials_and_targets_the_traces_path():
    headers = {h.get("name"): h for h in inbound().findall("set-header")}
    assert headers["Ocp-Apim-Subscription-Key"].get("exists-action") == "delete"
    assert headers["Authorization"].get("exists-action") == "delete"
    assert inbound().find("rewrite-uri").get("template") == "/tracer/v1/traces"
    assert inbound().find("set-backend-service").get("base-url").startswith("https://")
    assert inbound().find("base") is not None


def test_policy_contains_no_literal_secret():
    text = POLICY.read_text()
    assert not re.search(r"[0-9a-fA-F]{24,}|Bearer\s+\S{8,}", text)
    assert "{{fi-api-key}}" in text


def test_collector_follows_the_delivery_contract():
    assert COL["service"]["telemetry"]["metrics"]["level"] == "none"
    exp = COL["exporters"]["otlp_http/future_agi"]
    assert exp["compression"] == "none"
    assert exp["headers"] == {"X-Api-Key": "${env:FI_API_KEY}", "X-Secret-Key": "${env:FI_SECRET_KEY}"}
    assert exp["traces_endpoint"] == "${env:FI_TRACES_URL}"


def test_collector_is_traces_only_and_authenticated():
    assert list(COL["service"]["pipelines"]) == ["traces"]
    http = COL["receivers"]["otlp"]["protocols"]
    assert list(http) == ["http"] and http["http"]["auth"]["authenticator"] == "bearertokenauth/gateway"
    assert COL["extensions"]["bearertokenauth/gateway"]["token"] == "${env:GATEWAY_OTLP_TOKEN}"


def test_collector_sets_the_project_and_defaults_content_off():
    attrs = {a["key"]: a for a in COL["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"]["action"] == "upsert" and attrs["project_name"]["value"] == "${env:FI_PROJECT_NAME}"
    assert attrs["project_type"]["value"] == "observe"
    scrub = [s for s in COL["processors"]["transform/gateway"]["trace_statements"][0]["statements"] if "delete_matching_keys" in s]
    assert scrub and all('${env:FI_CAPTURE_CONTENT:-false}" != "true"' in s for s in scrub)
    assert "azure\\\\.ai_gateway\\\\.identity\\\\.claims" in COL_TEXT


def test_no_secret_values_in_the_config():
    assert not re.search(r"[0-9a-fA-F]{32,}", COL_TEXT)
