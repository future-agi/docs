"""Engineering-only acceptance: real ADK, real Collector, decoded wire, real backend mapper."""

import argparse
import ast
import copy
import http.server
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.request

import yaml
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

ROOT = Path(__file__).resolve().parents[1]
CANARY = b"CANARY_PRIVATE_7f8916"
COLLECTOR = Path(
    os.environ.get(
        "OTELCOL_CONTRIB", ROOT / "downloads/collector-0.164.0/otelcol-contrib"
    )
)
EVIDENCE = ROOT / "evidence"
EVIDENCE.mkdir(exist_ok=True)
ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": str(ROOT),
    "FI_API_KEY": "synthetic-api-key",
    "FI_SECRET_KEY": "synthetic-secret-key",
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server(forward=None):
    rows = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            rows.append(
                {"path": self.path, "headers": dict(self.headers), "body": body}
            )
            if forward:
                req = urllib.request.Request(
                    forward + self.path,
                    body,
                    {"Content-Type": "application/x-protobuf"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as response:
                        self.send_response(response.status)
                        self.end_headers()
                        self.wfile.write(response.read())
                except Exception:
                    self.send_response(503)
                    self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.end_headers()

        def log_message(self, *_):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, rows


def attrs(items):
    def value(v):
        key = v.WhichOneof("value")
        if key == "array_value":
            return [value(x) for x in v.array_value.values]
        if key == "kvlist_value":
            return attrs(v.kvlist_value.values)
        return getattr(v, key) if key else None

    return {x.key: value(x.value) for x in items}


def decode(rows):
    spans = []
    for row in rows:
        req = ExportTraceServiceRequest.FromString(row["body"])
        for rs in req.resource_spans:
            for ss in rs.scope_spans:
                for s in ss.spans:
                    spans.append(
                        {
                            "trace": s.trace_id.hex(),
                            "id": s.span_id.hex(),
                            "parent": s.parent_span_id.hex(),
                            "name": s.name,
                            "scope": ss.scope.name,
                            "resource": attrs(rs.resource.attributes),
                            "attrs": attrs(s.attributes),
                            "events": MessageToDict(s)["events"] if s.events else [],
                            "status": s.status.code,
                            "status_message": s.status.message,
                            "start_time": s.start_time_unix_nano,
                            "end_time": s.end_time_unix_nano,
                        }
                    )
    return spans


def assert_complete_traces(spans):
    """Check each trace independently; an unrelated root cannot hide an orphan."""
    by_id = {(s["trace"], s["id"]): s for s in spans}
    assert len(by_id) == len(spans), "duplicate export"
    for trace_id in {s["trace"] for s in spans}:
        roots = [s for s in spans if s["trace"] == trace_id and not s["parent"]]
        assert len(roots) == 1, "each trace must retain exactly one root"
    for span in spans:
        seen = {span["id"]}
        while span["parent"]:
            key = (span["trace"], span["parent"])
            assert key in by_id, "orphaned span or cross-trace parent"
            assert span["parent"] not in seen, "cyclic span ancestry"
            seen.add(span["parent"])
            span = by_id[key]


def backend():
    """Execute production mapper unchanged; isolate its database-heavy constant module.

    Only SpanAttributes is AST-extracted verbatim. No mapping/grouping logic is mocked.
    This is a normalization fixture, not a database/API/UI rendering test.
    """
    root = Path(os.environ["FUTUREAGI_BACKEND_ROOT"]) / "tracer/utils"
    for name in ("tracer", "tracer.utils", "tracer.utils.adapters"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    consts = ast.parse((root / "otel.py").read_text())
    cls = next(
        n
        for n in consts.body
        if isinstance(n, ast.ClassDef) and n.name == "SpanAttributes"
    )
    mod = types.ModuleType("tracer.utils.otel")
    exec(
        compile(ast.Module(body=[cls], type_ignores=[]), str(root / "otel.py"), "exec"),
        mod.__dict__,
    )
    sys.modules[mod.__name__] = mod

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    base = load("tracer.utils.adapters.base", root / "adapters/base.py")
    load("tracer.utils.adapters.otel_genai", root / "adapters/otel_genai.py")
    semantic = load(
        "tracer.utils.semantic_conventions", root / "semantic_conventions.py"
    )
    return base.normalize_span_attributes, semantic.get_attribute


def run_case(major, mode, capture=None, fail=False):
    name = f"v{major}-{mode}-{capture or 'unset'}" + ("-failclosed" if fail else "")
    sink, outgoing = server()
    port = free_port()
    proxy, incoming = server(f"http://127.0.0.1:{port}")
    cfg = yaml.safe_load((ROOT / "collector.yaml").read_text())
    cfg["receivers"]["otlp/adk"]["protocols"]["http"]["endpoint"] = f"127.0.0.1:{port}"
    cfg["exporters"]["otlp_http/futureagi"]["traces_endpoint"] = (
        f"http://127.0.0.1:{sink.server_port}/tracer/v1/traces"
    )
    if fail:
        statements = cfg["processors"]["transform/adk"]["trace_statements"][-1][
            "statements"
        ]
        statements.insert(
            0,
            'set(cache["bad"], ParseJSON(attributes["test.force_error"])) where attributes["test.force_error"] != nil',
        )
    config = EVIDENCE / f"{name}.yaml"
    config.write_text(yaml.safe_dump(cfg, sort_keys=False))
    log = (EVIDENCE / f"{name}.collector.log").open("w")
    proc = subprocess.Popen(
        [str(COLLECTOR), "--config=" + str(config)], env=ENV, stdout=log, stderr=log
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError(f"Collector startup failed: {name}")
                if time.monotonic() > deadline:
                    raise TimeoutError(name)
                threading.Event().wait(0.05)
        env = dict(
            ENV,
            TEST_ENDPOINT=f"http://127.0.0.1:{proxy.server_port}/v1/traces",
            OTEL_EXPORTER_OTLP_ENDPOINT=f"http://127.0.0.1:{proxy.server_port}",
        )
        if mode == "unavailable":
            env["TEST_ENDPOINT"] = f"http://127.0.0.1:{free_port()}/v1/traces"
        if capture is not None:
            env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = capture
        app = subprocess.run(
            [
                str(ROOT / f"tests/v{major}/probe"),
                "normal" if mode == "unavailable" else mode,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert app.returncode == 0, app.stderr
        summary = json.loads(app.stdout)
        baseline_env = dict(
            env,
            TEST_DISABLE_TELEMETRY="1",
            TEST_ENDPOINT=f"http://127.0.0.1:{free_port()}/v1/traces",
        )
        baseline = subprocess.run(
            [
                str(ROOT / f"tests/v{major}/probe"),
                "normal" if mode == "unavailable" else mode,
            ],
            env=baseline_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert baseline.returncode == 0, baseline.stderr
        baseline_summary = json.loads(baseline.stdout)
        assert all(
            summary[key] == baseline_summary[key]
            for key in ("runs", "events", "errors")
        ), (summary, baseline_summary)
        assert summary["shutdown_ms"] < 10000
        if mode in ("model-error", "cancel", "tool-cancel"):
            assert summary["errors"] == 1, summary
        else:
            assert summary["errors"] == 0, summary
        # ADK feeds a tool error back to the model as a function response.
        # It marks the tool span ERROR but does not abort the runner iterator.
        proc.terminate()
        proc.wait(timeout=12)
        all_raw, final = decode(incoming), decode(outgoing)
        # Keep actual protobuf for optional unchanged production-converter replay.
        combined = ExportTraceServiceRequest()
        for row in outgoing:
            request = ExportTraceServiceRequest.FromString(row["body"])
            combined.resource_spans.extend(request.resource_spans)
        (EVIDENCE / f"{name}.pb").write_bytes(combined.SerializeToString())
        raw = [s for s in all_raw if s["scope"] == "gcp.vertex.agent"]
        if mode == "parent":
            assert_complete_traces(final)
        if mode != "unavailable":
            assert any(s["scope"] == "application-owner" for s in all_raw), (
                "existing provider was shut down"
            )
            assert all(s["scope"] in ("gcp.vertex.agent", "application") for s in final)
        if mode == "unavailable":
            assert not incoming and not outgoing and summary["events"] > 0
        elif fail:
            assert incoming
            assert all(CANARY not in row["body"] for row in outgoing)
            # The canary-bearing batch must not be forwarded at all.
            bad = {s["id"] for s in raw if s["attrs"].get("test.force_error")}
            assert bad and not bad.intersection(s["id"] for s in final)
            assert (
                "failed to execute" in (EVIDENCE / f"{name}.collector.log").read_text()
            )
        else:
            assert raw and final, name
            assert {s["id"] for s in all_raw} == {s["id"] for s in final}, name
            assert_complete_traces(final)
            assert all(CANARY not in row["body"] for row in outgoing), (
                "private content leaked"
            )
            expected = {
                "invoke_agent": "AGENT",
                "generate_content": "LLM",
                "execute_tool": "TOOL",
                "invoke_workflow": "CHAIN",
                "invoke_node": "CHAIN",
                "application": "CHAIN",
            }
            byid = {s["id"]: s for s in all_raw}
            for span in final:
                original = byid[span["id"]]
                assert (
                    span["trace"] == original["trace"]
                    and span["parent"] == original["parent"]
                )
                assert (
                    span["start_time"]
                    == original["start_time"]
                    < span["end_time"]
                    == original["end_time"]
                )
                assert span["scope"] == (
                    "gcp.vertex.agent"
                    if original["scope"] == "gcp.vertex.agent"
                    else "application"
                )
                assert span["resource"] == {
                    "service.name": "google-adk-go",
                    "project_name": "google-adk-go",
                    "project_type": "observe",
                }
                a = span["attrs"]
                assert a["gen_ai.span.kind"] == expected[a["gen_ai.operation.name"]]
                original_attrs = original["attrs"]
                expected_session = (
                    original_attrs.get("session.id")
                    or original_attrs.get("gen_ai.conversation.id")
                    or original_attrs.get("adk.session.id")
                )
                if original["scope"] == "gcp.vertex.agent":
                    assert expected_session, "missing invocation session"
                assert a.get("session.id") == expected_session
                assert "adk.session.id" not in a
                if span["scope"] == "application":
                    assert set(a) <= {
                        "gen_ai.operation.name",
                        "gen_ai.span.kind",
                        "session.id",
                    }
                    assert span["name"] == "application"
                assert not span["events"] and not span["status_message"]
                if span["parent"]:
                    assert span["parent"] in byid
            if mode in (
                "normal",
                "parent",
                "stream",
                "privacy",
                "concurrent",
                "nested",
                "workflow",
            ):
                ops = [s["attrs"].get("gen_ai.operation.name") for s in final]
                assert (
                    "generate_content" in ops
                    and "execute_tool" in ops
                    and "invoke_agent" in ops
                )
                if mode == "normal":
                    assert (
                        ops.count("invoke_agent") == 1
                        and ops.count("generate_content") == 2
                        and ops.count("execute_tool") == 1
                    ), ops
                if mode == "workflow":
                    assert "invoke_workflow" in ops and "invoke_node" in ops
                for s in final:
                    if s["attrs"].get("gen_ai.operation.name") == "generate_content":
                        assert s["attrs"]["gen_ai.request.model"] == "gemini-test"
                        assert s["attrs"]["gen_ai.usage.input_tokens"] == 11
                        assert s["attrs"]["gen_ai.usage.output_tokens"] == 9
                        assert s["attrs"]["gen_ai.response.finish_reasons"]
            if mode in ("model-error", "tool-error", "cancel", "tool-cancel"):
                operation = (
                    "execute_tool"
                    if mode in ("tool-error", "tool-cancel")
                    else "generate_content"
                )
                failures = [
                    s
                    for s in final
                    if s["attrs"].get("gen_ai.operation.name") == operation
                ]
                assert failures and all(
                    s["status"] == 2 and s["attrs"].get("error.type") for s in failures
                ), failures
            if mode == "concurrent":
                sessions = [
                    s["attrs"].get("session.id")
                    for s in final
                    if s["attrs"].get("gen_ai.operation.name") == "invoke_agent"
                ]
                assert sorted(sessions) == ["session-a", "session-a", "session-b"], (
                    sessions
                )
                for agent_span in (
                    s
                    for s in final
                    if s["attrs"].get("gen_ai.operation.name") == "invoke_agent"
                ):
                    members = [s for s in final if s["trace"] == agent_span["trace"]]
                    assert len(members) == (5 if major == "2-latest" else 4)
                    assert all(
                        s["attrs"].get("session.id")
                        == agent_span["attrs"]["session.id"]
                        for s in members
                    )
            if mode in ("normal", "stream"):
                contents = [
                    s["attrs"]
                    for s in raw
                    if s["attrs"].get("gen_ai.operation.name") == "generate_content"
                ]
                if str(major).startswith("2") and capture == "SPAN_ONLY":
                    assert all("gen_ai.input.messages" in a for a in contents)
                    assert any(
                        "Settled " in str(a.get("gen_ai.output.messages", ""))
                        for a in contents
                    )
                else:
                    assert all(
                        "gen_ai.input.messages" not in a
                        and "gen_ai.output.messages" not in a
                        for a in contents
                    )
            if os.environ.get("FUTUREAGI_BACKEND_ROOT"):
                rows = [{"attributes": copy.deepcopy(s["attrs"])} for s in final]
                normalize, get_attribute = backend()
                normalize(rows)
                for original, row in zip(final, rows):
                    a = row["attributes"]
                    assert (
                        get_attribute(a, "span_kind")
                        == original["attrs"]["gen_ai.span.kind"]
                    )
                    assert get_attribute(a, "session_id") == original["attrs"].get(
                        "session.id"
                    )
                    if (
                        a["gen_ai.span.kind"] == "LLM"
                        and "gen_ai.usage.input_tokens" in a
                    ):
                        assert (
                            a["llm.token_count.prompt"]
                            == a["gen_ai.usage.input_tokens"]
                        )
                        assert (
                            a["llm.token_count.completion"]
                            == a["gen_ai.usage.output_tokens"]
                        )
        assert all(r["path"] == "/v1/traces" for r in incoming), (
            "unexpected signal from ADK"
        )
        for row in outgoing:
            h = {k.lower(): v for k, v in row["headers"].items()}
            assert row["path"] == "/tracer/v1/traces"
            assert h["content-type"] == "application/x-protobuf"
            assert (
                h["x-api-key"] == ENV["FI_API_KEY"]
                and h["x-secret-key"] == ENV["FI_SECRET_KEY"]
            )
        data = {
            "name": name,
            "status": "PASS",
            "summary": summary,
            "raw": raw,
            "outgoing": final,
        }
        (EVIDENCE / f"{name}.json").write_text(json.dumps(data, indent=2))
        return {
            "name": name,
            "status": "PASS",
            "raw_spans": len(raw),
            "exported_spans": len(final),
            "backend_fixture": "PASS"
            if os.environ.get("FUTUREAGI_BACKEND_ROOT")
            and mode != "unavailable"
            and not fail
            else "NOT_RUN",
            **summary,
        }
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=12)
        log.close()
        sink.shutdown()
        proxy.shutdown()
        sink.server_close()
        proxy.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    cases = [(major, "normal", None, False) for major in (1, 2, "2-latest")]
    if not args.quick:
        cases = [
            (major, mode, None, False)
            for major in (1, 2, "2-latest")
            for mode in (
                "normal",
                "parent",
                "nested",
                "privacy",
                "concurrent",
                "model-error",
                "tool-error",
                "tool-cancel",
                "cancel",
                "stream",
                "early",
                "unavailable",
            )
        ]
        cases += [(major, "workflow", None, False) for major in (2, "2-latest")]
        cases += [
            (major, "normal", capture, False)
            for major in (2, "2-latest")
            for capture in ("false", "true", "EVENT_ONLY", "SPAN_ONLY")
        ]
        cases += [(major, "stream", "SPAN_ONLY", False) for major in (2, "2-latest")]
        cases += [(1, "normal", "true", False)]
        cases += [(major, "malformed", None, True) for major in (1, 2, "2-latest")]
    results = []
    for case in cases:
        try:
            result = run_case(*case)
        except Exception as exc:
            import traceback

            result = {
                "case": case,
                "status": "FAIL",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        results.append(result)
        print(json.dumps(result), flush=True)
        (EVIDENCE / "acceptance.json").write_text(json.dumps(results, indent=2))
    return int(any(r["status"] != "PASS" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
