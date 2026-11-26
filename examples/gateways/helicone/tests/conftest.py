import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from support.mock_helicone import MockHelicone  # noqa: E402
from support.otlp_capture import OtlpCapture  # noqa: E402

HELICONE_KEY = "sk-helicone-test-key"
PROVIDER_KEY = "sk-provider-test-key"
FI_KEY = "fi-test-api-key"
FI_SECRET = "fi-test-secret-key"
PROJECT = "helicone-conformance"
MARKER = "HELI-MARK-4f9a1c7e"
TOOL_MARKER = "HELI-TOOLDEF-4f9a1c7e"
ERROR_MARKER = "UPSTREAM-ERROR-BODY-MARKER"


@pytest.fixture()
def mock():
    with MockHelicone(HELICONE_KEY) as m:
        yield m


@pytest.fixture()
def capture():
    with OtlpCapture() as c:
        yield c


class Run:
    def __init__(self, proc, capture, mock):
        self.proc, self.capture, self.mock = proc, capture, mock
        self.summary = None
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
        if lines:
            self.summary = json.loads(lines[-1])

    @property
    def spans(self):
        return list(self.capture.spans)

    def by_kind(self, kind):
        return [s for s in self.spans if s.attributes.get("gen_ai.span.kind") == kind]

    def dump(self) -> str:
        """Everything the collector received, as one string: resource, attributes, events, status."""
        return json.dumps([s.to_dict() for s in self.spans], default=str)


@pytest.fixture()
def run_python(mock, capture):
    def _run(surface="gateway", args=(), env=None, expect_spans=1):
        e = dict(os.environ)
        for k in list(e):
            if k.startswith(("FI_HIDE", "HELICONE_", "OTEL_")):
                del e[k]
        e.update(
            FI_BASE_URL=capture.url,
            FI_API_KEY=FI_KEY,
            FI_SECRET_KEY=FI_SECRET,
            HELICONE_SURFACE=surface,
            HELICONE_BASE_URL=mock.gateway_base_url if surface == "gateway" else mock.proxy_base_url,
            HELICONE_API_KEY=HELICONE_KEY,
            OPENAI_API_KEY=PROVIDER_KEY,
            HELICONE_MODEL="openai/gpt-4o-mini",
            PYTHONDONTWRITEBYTECODE="1",
        )
        e.update(env or {})
        proc = subprocess.run(
            [sys.executable, str(ROOT / "python" / "run_demo.py"), "--project", PROJECT, "--marker", MARKER, *args],
            env=e,
            capture_output=True,
            text=True,
            timeout=120,
        )
        capture.wait_for_spans(expect_spans, timeout=10)
        return Run(proc, capture, mock)

    return _run
