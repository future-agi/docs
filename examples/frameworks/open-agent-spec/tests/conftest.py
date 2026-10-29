"""Shared fixtures: run app.py for real (pyagentspec + LangGraph adapter + traceAI) against a
deterministic model stand-in and a loopback OTLP recorder. No network beyond 127.0.0.1."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(EXAMPLE))

from fake_openai import FakeOpenAI  # noqa: E402
from otlp_recorder import Recorder  # noqa: E402

SYSTEM_PROMPT_PHRASE = "Call get_weather before you answer"


@dataclass
class Run:
    returncode: int
    stdout: str
    stderr: str
    recorder: Recorder
    env: dict

    def spans(self) -> list[dict]:
        return self.recorder.spans()


@pytest.fixture
def marker() -> str:
    return "MARK-" + secrets.token_hex(6)


@pytest.fixture
def run_app():
    """Call ``run_app(scenario, question, **env)`` -> Run."""
    stack = []

    def _run(scenario: str, question: str, **extra_env: str) -> Run:
        model_key = "model-key-" + secrets.token_hex(8)
        recorder = Recorder().__enter__()
        fake = FakeOpenAI(model_key).__enter__()
        stack.extend([recorder, fake])
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("FI_", "OTEL_", "MODEL_", "OPENAI_"))
        }
        env.update(
            FI_API_KEY="fi-api-" + secrets.token_hex(8),
            FI_SECRET_KEY="fi-secret-" + secrets.token_hex(8),
            FI_BASE_URL=recorder.origin,
            FI_PROJECT_NAME="oas-test",
            MODEL_BASE_URL=fake.url,
            MODEL_API_KEY=model_key,
            MODEL_ID="fake-model",
            MODEL_BAD_API_KEY="bad-model-key-" + secrets.token_hex(8),
            PYTHONUNBUFFERED="1",
        )
        env.update(extra_env)
        proc = subprocess.run(
            [sys.executable, str(EXAMPLE / "app.py"), scenario, question],
            cwd=str(EXAMPLE),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        return Run(proc.returncode, proc.stdout, proc.stderr, recorder, env)

    yield _run
    for item in reversed(stack):
        item.__exit__(None, None, None)


def by_name(spans: list[dict], name: str) -> list[dict]:
    return [s for s in spans if s["name"] == name]


def kind(span: dict) -> str:
    return span["attributes"].get("gen_ai.span.kind", "")
