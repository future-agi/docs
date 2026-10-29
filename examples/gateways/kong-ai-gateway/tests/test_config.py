"""Static checks on the shipped kong.yml (no network needed)."""
from pathlib import Path

import yaml  # PyYAML

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "kong.yml").read_text().replace("${LOG_PAYLOADS}", "false"))


def otel():
    return next(p for p in CFG["plugins"] if p["name"] == "opentelemetry")["config"]


def test_project_attributes_are_set_on_the_plugin():
    ra = otel()["resource_attributes"]
    assert ra["project_name"] and ra["project_type"] == "observe"


def test_auth_headers_are_the_future_agi_pair_and_not_langfuse_or_bearer():
    h = otel()["headers"]
    assert set(h) == {"X-Api-Key", "X-Secret-Key"}


def test_traces_only_no_metrics_or_logs_endpoints():
    c = otel()
    assert "metrics" not in c and "logs_endpoint" not in c


def test_payload_logging_is_a_parameter_default_off_in_docs():
    svc = CFG["services"][0]
    logging = next(p for p in svc["plugins"] if p["name"] == "ai-proxy")["config"]["logging"]
    assert logging["log_statistics"] is True and logging["log_payloads"] is False
