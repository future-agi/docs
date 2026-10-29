import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FIXTURE_FI_API_KEY = "fi-api-key-FIXTURE-1f3a"
FIXTURE_FI_SECRET_KEY = "fi-secret-key-FIXTURE-9c2d"
FIXTURE_MODEL_KEY = "sk-model-key-FIXTURE-77be"


# activities.py builds its OpenAI client when it is imported, which happens while pytest collects the tests.
os.environ.setdefault("OPENAI_API_KEY", FIXTURE_MODEL_KEY)


def temporal_cli() -> str | None:
    """Path of the Temporal CLI that starts the local dev server, or None."""
    return os.environ.get("TEMPORAL_CLI") or shutil.which("temporal")


needs_temporal = pytest.mark.skipif(
    temporal_cli() is None or os.environ.get("RUN_TEMPORAL_TESTS") != "1",
    reason="set RUN_TEMPORAL_TESTS=1 and install the Temporal CLI (or set TEMPORAL_CLI) to run the dev-server tests",
)


@pytest.fixture(autouse=True)
def fixture_env(monkeypatch):
    """Fixture keys and an unreachable Future AGI: nothing in the unit tests touches the network."""
    monkeypatch.setenv("FI_API_KEY", FIXTURE_FI_API_KEY)
    monkeypatch.setenv("FI_SECRET_KEY", FIXTURE_FI_SECRET_KEY)
    monkeypatch.setenv("FI_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("FI_PROJECT_NAME", "temporal-test")
    monkeypatch.setenv("OPENAI_API_KEY", FIXTURE_MODEL_KEY)
    for name in ("KEEP_TEMPORAL_ERROR_TEXT", "FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_INPUT_MESSAGES",
                 "FI_HIDE_OUTPUT_MESSAGES", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        monkeypatch.delenv(name, raising=False)


def reset_otel() -> None:
    """OpenTelemetry lets the global tracer provider be set once per process, and traceAI instruments
    the openai package once. Undo both, so that a test can build its own provider."""
    from opentelemetry import trace

    try:
        from traceai_openai import OpenAIInstrumentor

        OpenAIInstrumentor().uninstrument()
    except Exception:  # noqa: BLE001 - the instrumentor may never have been installed
        pass
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace._TRACER_PROVIDER = None


@pytest.fixture
def fresh_otel():
    reset_otel()
    yield
    reset_otel()
