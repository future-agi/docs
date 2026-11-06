"""Graphite's setup_tracing() builds a plaintext gRPC exporter with no headers and sets service.name
instead of project_name. It must never be in the path (AC-02)."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest
from conftest import MODEL_KEY, ROOT

SOURCES = [p for p in ROOT.glob("*.py")]


def test_there_are_sources_to_check():
    assert {p.name for p in SOURCES} >= {"futureagi_grafi.py", "quickstart.py", "app.py"}


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_source_file_uses_setup_tracing(path: Path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "setup_tracing", f"{path.name}:{node.lineno} refers to setup_tracing"
        elif isinstance(node, ast.Attribute):
            assert node.attr != "setup_tracing", f"{path.name}:{node.lineno} refers to setup_tracing"
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
            assert not any("instrumentations.tracing" in n or n == "setup_tracing" for n in names), f"{path.name}:{node.lineno}"


def test_a_run_never_reaches_setup_tracing(model, monkeypatch):
    """Make every entry point of the helper raise, then run the quickstart path in this process."""
    import asyncio

    import grafi.common.instrumentations.tracing as helper

    def boom(*args, **kwargs):
        raise AssertionError("grafi's setup_tracing was called")

    for name in ("setup_tracing", "_setup_otlp_tracing", "_setup_auto_tracing", "_setup_in_memory_tracing"):
        monkeypatch.setattr(helper, name, boom)
    monkeypatch.setenv("OPENAI_API_KEY", MODEL_KEY)
    monkeypatch.setenv("OPENAI_BASE_URL", model.url)
    monkeypatch.setenv("OPENAI_MODEL", "fake-model")
    monkeypatch.setenv("FI_API_KEY", "k")
    monkeypatch.setenv("FI_SECRET_KEY", "s")
    monkeypatch.setenv("FI_BASE_URL", "http://127.0.0.1:9")  # nothing listens: export errors are logged, not raised
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "1")
    import quickstart

    asyncio.run(quickstart.main())


def test_the_recipe_leaves_the_global_tracer_provider_alone():
    from futureagi_grafi import create_tracer_provider
    from opentelemetry import trace

    before = trace.get_tracer_provider()
    provider = create_tracer_provider("p", api_key="k", secret_key="s", base_url="http://127.0.0.1:9")
    try:
        assert trace.get_tracer_provider() is before
        assert provider.resource.attributes["project_name"] == "p"
        assert "service.name" in provider.resource.attributes  # the SDK default, which Future AGI does not read
    finally:
        provider.shutdown()


def test_exporter_arguments_without_a_collector(monkeypatch):
    """The constructor arguments, captured instead of read back from the exporter's private fields."""
    import futureagi_grafi
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import Compression

    captured = {}

    class Recorder:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def export(self, spans):  # pragma: no cover - never reached
            raise AssertionError

        def shutdown(self):
            pass

        def force_flush(self, timeout_millis=0):
            return True

    monkeypatch.setattr(futureagi_grafi, "OTLPSpanExporter", Recorder)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_COMPRESSION", "gzip")
    monkeypatch.delenv("FI_BASE_URL", raising=False)
    provider = futureagi_grafi.create_tracer_provider("p", api_key="k", secret_key="s")
    provider.shutdown()
    assert captured["endpoint"] == "https://api.futureagi.com/tracer/v1/traces"
    assert captured["compression"] is Compression.NoCompression
    assert captured["headers"] == {"X-Api-Key": "k", "X-Secret-Key": "s"}
