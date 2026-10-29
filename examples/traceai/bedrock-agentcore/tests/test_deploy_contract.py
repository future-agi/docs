"""Deployment wiring only; no AWS resources or real credentials are used."""
import inspect
import os
from pathlib import Path
import re
import runpy
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parents[1]
PAGE = HERE.parents[2] / "src/pages/docs/integrations/traceai/bedrock-agentcore.mdx"


def test_page_and_deployment_file_match():
    page = PAGE.read_text()
    block = re.search(r'```python title="deploy.py"\n(.*?)\n```', page, re.S)
    assert block and block.group(1) == (HERE / "deploy.py").read_text().rstrip()
    assert 'bedrock-agentcore-starter-toolkit==0.3.14' in page
    assert not re.search(r"not tested|untested|unverified", page, re.I)


@pytest.mark.parametrize("entrypoint", ["agent_langchain.py", "agent_strands.py"])
def test_required_keys_and_model_config_reach_runtime(monkeypatch, entrypoint):
    # Install requirements-deploy.txt to also verify published API signatures.
    toolkit = pytest.importorskip("bedrock_agentcore_starter_toolkit")
    configure_signature = inspect.signature(toolkit.Runtime.configure)
    launch_signature = inspect.signature(toolkit.Runtime.launch)
    calls = {}

    class Runtime:
        def configure(self, **kwargs):
            configure_signature.bind(self, **kwargs)
            calls["configure"] = kwargs

        def launch(self, **kwargs):
            launch_signature.bind(self, **kwargs)
            calls["launch"] = kwargs

    monkeypatch.setitem(sys.modules, "bedrock_agentcore_starter_toolkit", SimpleNamespace(Runtime=Runtime))
    for key, value in {
        "FI_API_KEY": "fixture-api", "FI_SECRET_KEY": "fixture-secret",
        "OPENAI_API_KEY": "fixture-model", "OPENAI_BASE_URL": "https://provider.example/v1",
        "AGENT_MODEL": "fixture-model-id", "AGENT_ENTRYPOINT": entrypoint,
        "FI_BASE_URL": "https://api.futureagi.com", "FI_PROJECT_NAME": "fixture-project",
    }.items():
        monkeypatch.setenv(key, value)
    runpy.run_path(str(HERE / "deploy.py"))
    assert calls["configure"]["entrypoint"] == entrypoint
    assert calls["configure"]["disable_otel"] is True
    env = calls["launch"]["env_vars"]
    assert env["OPENAI_API_KEY"] == "fixture-model"
    assert env["OPENAI_BASE_URL"] == "https://provider.example/v1"
    assert env["AGENT_MODEL"] == "fixture-model-id"
    if entrypoint == "agent_langchain.py":
        assert env["FI_API_KEY"] == "fixture-api" and env["FI_SECRET_KEY"] == "fixture-secret"
    else:
        assert env["OTEL_EXPORTER_OTLP_HEADERS"] == "X-Api-Key=fixture-api,X-Secret-Key=fixture-secret"
        assert env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] == "https://api.futureagi.com/tracer/v1/traces"


def test_missing_secret_fails_before_runtime_creation(monkeypatch):
    monkeypatch.delenv("FI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "bedrock_agentcore_starter_toolkit", SimpleNamespace(Runtime=lambda: pytest.fail("created runtime before key validation")))
    with pytest.raises(KeyError, match="FI_API_KEY"):
        runpy.run_path(str(HERE / "deploy.py"))
