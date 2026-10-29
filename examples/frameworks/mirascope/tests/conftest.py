"""Fixtures: run app.py for real, as a subprocess, against a fake model and a recording collector.

Nothing here needs a key or the network. The model is tests/fake_openai.py (a stand-in, not a
model). What is real: Mirascope 2.5.0, its ops.instrument_llm spans, OpenTelemetry's OTLP/HTTP
exporter, and futureagi_tracing.py. The collector is tests/recorder.py, which keeps the bytes it
receives.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fake_openai import FakeOpenAI  # noqa: E402
from recorder import Recorder  # noqa: E402

HERE = Path(__file__).resolve().parent.parent

# Unique strings the privacy tests search for in everything that is exported.
MARKER = "Zq7Marker4471"
FI_API_KEY = "fi-test-api-key-AAAA1111"
FI_SECRET_KEY = "fi-test-secret-key-BBBB2222"
MODEL_API_KEY = "sk-test-model-key-CCCC3333"
MODEL_ID = "openai/fake-model:completions"  # ":completions" pins Mirascope to /chat/completions


@dataclass
class Run:
    scenario: str
    returncode: int
    stdout: str
    stderr: str
    spans: list[dict]
    raw_bodies: list[bytes]
    requests: list[dict] = field(default_factory=list)
    received: list[dict] = field(default_factory=list)
    model_requests: list[dict] = field(default_factory=list)

    def span(self, name_prefix: str) -> dict:
        matches = [s for s in self.spans if s["name"].startswith(name_prefix)]
        assert len(matches) == 1, f"expected one span named {name_prefix!r}, got {[s['name'] for s in self.spans]}"
        return matches[0]

    def everything(self) -> str:
        """All exported text: the decoded spans plus the raw request bytes (latin-1 so bytes survive)."""
        decoded = repr(self.spans)
        raw = b"\n".join(self.raw_bodies).decode("latin-1")
        return decoded + "\n" + raw


def _run(
    argv: list[str],
    *,
    label: str,
    capture_content: bool = False,
    usage: bool = True,
    project: str = "mirascope-test",
    extra_env: dict[str, str] | None = None,
) -> Run:
    """Run a command in the example directory with the fake model and the recording collector."""
    fake = FakeOpenAI(usage=usage).start()
    recorder = Recorder().start()
    try:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("FI_", "OPENAI_", "OTEL_", "MIRASCOPE_"))
        }
        env.update(
            FI_API_KEY=FI_API_KEY,
            FI_SECRET_KEY=FI_SECRET_KEY,
            FI_BASE_URL=recorder.base_url,
            FI_PROJECT_NAME=project,
            OPENAI_API_KEY=MODEL_API_KEY,
            OPENAI_BASE_URL=fake.base_url,
            MIRASCOPE_MODEL=MODEL_ID,
            DEMO_CITY=MARKER,
            PYTHONPATH=str(HERE),
        )
        if capture_content:
            env["FI_CAPTURE_CONTENT"] = "1"
        env.update(extra_env or {})
        done = subprocess.run(argv, cwd=HERE, env=env, capture_output=True, text=True, timeout=120)
        return Run(
            scenario=label,
            returncode=done.returncode,
            stdout=done.stdout,
            stderr=done.stderr,
            spans=recorder.spans(),
            raw_bodies=recorder.raw_bodies(),
            received=list(recorder.received),
            model_requests=list(fake.requests),
        )
    finally:
        recorder.stop()
        fake.stop()


def run_scenario(scenario: str, **kwargs) -> Run:
    return _run([sys.executable, str(HERE / "app.py"), scenario], label=scenario, **kwargs)


def run_code(code: str, **kwargs) -> Run:
    """Run a snippet (as ``python -c``) instead of app.py, with the same fakes."""
    return _run([sys.executable, "-c", code], label="code", **kwargs)


@pytest.fixture(scope="session")
def runs():
    """Lazily run and cache each (scenario, content mode) once per test session."""
    cache: dict[tuple, Run] = {}

    def get(scenario: str, *, capture_content: bool = False, usage: bool = True, project: str = "mirascope-test") -> Run:
        key = (scenario, capture_content, usage, project)
        if key not in cache:
            cache[key] = run_scenario(scenario, capture_content=capture_content, usage=usage, project=project)
        return cache[key]

    return get
