"""Shared helpers for the LiteLLM Proxy example tests (stdlib only)."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import otlp_contract as oc  # noqa: E402


def fixture(name: str):
    """(spans, meta, docs) for a committed capture."""
    docs = [json.loads((FIXTURES / f"{name}.json").read_text())]
    meta = json.loads((FIXTURES / f"{name}.meta.json").read_text())
    return oc.flatten(docs), meta, docs


def chat_spans(spans):
    return [s for s in spans if s.attrs.get("gen_ai.operation.name") == "chat"]


def serve_in_thread(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
