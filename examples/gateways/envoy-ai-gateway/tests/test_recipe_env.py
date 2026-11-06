"""Offline test: run_aigw.sh exports exactly the documented environment for aigw.

A stub `aigw` executable dumps its environment, so no gateway, network or keys are needed."""
import os, stat, subprocess, tempfile, pathlib, json

HERE = pathlib.Path(__file__).resolve().parent.parent
BASE = {"PATH": os.environ["PATH"], "FI_API_KEY": "pk-test", "FI_SECRET_KEY": "sk-test", "OPENAI_API_KEY": "up-test"}


def run(extra=None):
    with tempfile.TemporaryDirectory() as d:
        stub = pathlib.Path(d, "aigw")
        stub.write_text('#!/bin/sh\nenv > "$0.env"\necho "ARGS:$*" >> "$0.env"\n')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        r = subprocess.run([str(HERE / "run_aigw.sh"), str(stub)], env={**BASE, **(extra or {})}, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        lines = pathlib.Path(str(stub) + ".env").read_text().splitlines()
    env = dict(l.split("=", 1) for l in lines if "=" in l and not l.startswith("ARGS:"))
    env["__args"] = [l for l in lines if l.startswith("ARGS:")][0]
    return env


def test_transport_and_auth_are_http_with_both_key_headers():
    e = run()
    assert e["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"
    assert e["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4318"      # not the 4317 gRPC port
    assert e["OTEL_EXPORTER_OTLP_HEADERS"] == "X-Api-Key=pk-test,X-Secret-Key=sk-test"
    assert "Authorization" not in e["OTEL_EXPORTER_OTLP_HEADERS"]            # collector rejects Bearer


def test_project_name_is_a_resource_attribute():
    e = run({"FI_PROJECT_NAME": "my-proj"})
    assert e["OTEL_RESOURCE_ATTRIBUTES"] == "project_name=my-proj,project_type=observe"


def test_metrics_and_logs_off_collector_is_traces_only():
    e = run()
    assert e["OTEL_METRICS_EXPORTER"] == "none"
    assert e["OTEL_LOGS_EXPORTER"] == "none"   # aigw otherwise auto-wires gRPC OTLP access logs and refuses http/protobuf


def test_content_is_off_by_default_and_opt_in_turns_it_on():
    off = run()
    for k in ("INPUTS", "OUTPUTS", "EMBEDDINGS_TEXT", "EMBEDDINGS_VECTORS"):
        assert off[f"OPENINFERENCE_HIDE_{k}"] == "true"
    on = run({"FI_CAPTURE_CONTENT": "1"})
    for k in ("INPUTS", "OUTPUTS", "EMBEDDINGS_TEXT", "EMBEDDINGS_VECTORS"):
        assert on[f"OPENINFERENCE_HIDE_{k}"] == "false"


def test_keys_are_required():
    r = subprocess.run([str(HERE / "run_aigw.sh"), "true"], env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
    assert r.returncode != 0 and "FI_API_KEY" in r.stderr
