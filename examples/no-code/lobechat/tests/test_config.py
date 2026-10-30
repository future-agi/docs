"""Static checks of the shipped files and of the docs page that prints them."""

import re
import subprocess

import yaml

from conftest import EXAMPLE, REPO

CONFIG = EXAMPLE / "otelcol" / "otelcol.yaml"
OVERRIDE = EXAMPLE / "docker-compose.override.yml.example"
ENV = EXAMPLE / "env" / "futureagi.env.example"
COMPOSE_TEST = EXAMPLE / "compose.test.yml"
PAGE = REPO / "src" / "pages" / "docs" / "integrations" / "no-code" / "lobechat.mdx"


def load(path):
    return yaml.safe_load(path.read_text())


def code_blocks(text):
    return [m.group(2) for m in re.finditer(r"```(\w+)\n(.*?)\n```", text, re.S)]


# ---- collector -------------------------------------------------------------------------------------------
def test_collector_telemetry_metrics_off_and_uncompressed_export():
    c = load(CONFIG)
    assert c["service"]["telemetry"]["metrics"]["level"] == "none"
    otlp = {k: v for k, v in c["exporters"].items() if k.startswith(("otlp", "otlphttp"))}
    assert otlp and all(v.get("compression") == "none" for v in otlp.values())
    assert all(v.get("encoding", "proto") == "proto" for v in otlp.values())


def test_collector_holds_no_credentials():
    text = CONFIG.read_text()
    c = load(CONFIG)
    setter = c["extensions"]["headers_setter/future_agi"]["headers"]
    assert {h["key"]: h.get("from_context") for h in setter} == {"X-Api-Key": "x-api-key",
                                                                  "X-Secret-Key": "x-secret-key"}
    assert not any("value" in h for h in setter)
    assert c["receivers"]["otlp"]["protocols"]["http"]["include_metadata"] is True
    assert set(c["processors"]["batch"]["metadata_keys"]) == {"x-api-key", "x-secret-key"}
    assert not re.search(r"(?i)(api[_-]?key|secret)[^\n]*[:=]\s*['\"]?[A-Za-z0-9]{16,}", text)


def test_content_off_is_the_default():
    text = CONFIG.read_text()
    flags = re.findall(r"\$\{env:FI_CAPTURE_CONTENT(:-[a-z]+)?\}", text)
    assert flags and all(f == ":-false" for f in flags)
    statements = "\n".join(load(CONFIG)["processors"]["transform/lobehub"]["trace_statements"][0]["statements"])
    for key in ("gen_ai.agent.description", "status.message", "tool\\\\.call\\\\.(arguments|result)",
                "input\\\\.messages", "system_instructions"):
        assert key in statements, key


def test_pipelines():
    c = load(CONFIG)
    traces = c["service"]["pipelines"]["traces"]
    assert traces["processors"][0] == "filter/keep_agent_runs"
    assert traces["processors"][-1] == "batch"
    assert traces["exporters"] == ["otlp_http/future_agi"]
    assert c["service"]["pipelines"]["metrics"]["exporters"] == ["nop"]
    assert "logs" not in c["service"]["pipelines"]
    attrs = {a.get("key") or a.get("pattern"): a["action"] for a in c["processors"]["resource/future_agi"]["attributes"]}
    assert attrs["project_name"] == "upsert" and attrs["^(host|os|process|container)\\..*"] == "delete"


# ---- LobeHub side ----------------------------------------------------------------------------------------
def test_env_block():
    env = dict(line.split("=", 1) for line in ENV.read_text().splitlines() if line and not line.startswith("#"))
    assert env["ENABLE_TELEMETRY"] == "1"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://futureagi-otelcol:4318"
    assert env["OTEL_EXPORTER_OTLP_TRACES_HEADERS"].startswith("X-Api-Key=")
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env  # keys go with traces only, never with metrics
    assert env["OTEL_NODE_RESOURCE_DETECTORS"] == "env"
    assert int(env["OTEL_METRICS_EXPORTER_INTERVAL"]) >= 60000


def test_override():
    o = load(OVERRIDE)["services"]
    col = o["futureagi-otelcol"]
    assert col["image"] == "otel/opentelemetry-collector-contrib:0.162.0"
    assert "ports" not in col
    assert "FI_CAPTURE_CONTENT=false" in col["environment"]
    assert col["networks"] == ["lobe-network"]
    assert o["lobe"]["depends_on"]["futureagi-otelcol"]["condition"] == "service_started"


def test_test_stack_memory_caps():
    services = load(COMPOSE_TEST)["services"]
    limits = {name: s["mem_limit"] for name, s in services.items()}
    to_mb = {k: int(v.rstrip("m")) for k, v in limits.items()}
    assert set(to_mb) == {"postgresql", "redis", "gateway", "lobe", "futureagi-otelcol"}
    assert max(to_mb.values()) <= 768 and sum(to_mb.values()) <= 2048


def test_run_script_syntax():
    subprocess.run(["bash", "-n", str(EXAMPLE / "run_e2e.sh")], check=True)


# ---- docs page -------------------------------------------------------------------------------------------
def test_page_prints_the_shipped_files_verbatim():
    blocks = code_blocks(PAGE.read_text())
    assert OVERRIDE.read_text().rstrip("\n") in blocks
    assert CONFIG.read_text().rstrip("\n") in blocks
    assert ENV.read_text().rstrip("\n") in blocks


def test_page_has_customer_setup_and_safety_contract():
    text = PAGE.read_text()
    for phrase in ("## 1. Add the collector", "## 2. Point LobeHub at it", "## 3. Run an agent and open Observe",
                   "## What is captured", "## Privacy", "## Troubleshooting", "## Limitations",
                   "## How this differs from related integrations", "v2.2.18 or v2.2.19", "Agent Gateway", "FI_CAPTURE_CONTENT=false",
                   "Keep port 4318 on the private Compose network"):
        assert phrase in text, phrase
    assert "## Run the test yourself" not in text
    assert "| Tested with |" not in text
