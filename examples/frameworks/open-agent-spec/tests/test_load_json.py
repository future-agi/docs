"""An Agent Spec definition loaded from JSON (``load_json``) is traced like ``load_component``."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from conftest import kind
from fake_openai import FakeOpenAI
from otlp_recorder import Recorder

PROBE = Path(__file__).resolve().parent / "load_json_probe.py"


def test_load_json_gives_the_same_tree_and_keeps_the_key_out():
    key = "model-key-" + secrets.token_hex(8)
    with Recorder() as recorder, FakeOpenAI(key) as fake:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FI_", "OTEL_", "MODEL_"))}
        env.update(FI_API_KEY="fi-a", FI_SECRET_KEY="fi-b", FI_BASE_URL=recorder.origin,
                   FI_PROJECT_NAME="oas-json", MODEL_BASE_URL=fake.url, MODEL_API_KEY=key,
                   MODEL_ID="fake-model")
        out = subprocess.run([sys.executable, str(PROBE)], env=env, capture_output=True,
                             text=True, timeout=180)
        assert out.returncode == 0, out.stderr[-2000:]
        facts = json.loads(out.stdout.strip().splitlines()[-1])
        spans = recorder.spans()
        raw = recorder.raw()
    assert facts == {"key_in_json": False, "component_ref": True}
    assert len({s["traceId"] for s in spans}) == 1
    assert sorted(kind(s) for s in spans) == ["CHAIN"] * 4 + ["LLM"] * 2 + ["TOOL"]
    assert [s["name"] for s in spans if not s["parentSpanId"]] == ["weather_assistant"]
    assert key.encode() not in raw
