"""Run the exact customer applications against loopback Gemini + real OTLP Collector."""

import http.server
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import threading
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "acceptance", ROOT / "tests/acceptance.py"
)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def test(major):
    requests = []

    class Gemini(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": body})
            done = any(
                "functionResponse" in part
                for c in body["contents"]
                for part in c["parts"]
            )
            part = (
                {"text": "There are 24 NOTEBOOK-A5 notebooks available."}
                if done
                else {
                    "functionCall": {
                        "id": "inventory-call",
                        "name": "get_stock",
                        "args": {"sku": "NOTEBOOK-A5"},
                    }
                }
            )
            response = {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [part]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 18,
                },
                "modelVersion": "gemini-test",
            }
            data = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    gemini = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gemini)
    threading.Thread(target=gemini.serve_forever, daemon=True).start()
    sink, outgoing = a.server()
    port = a.free_port()
    cfg = yaml.safe_load((ROOT / "collector.yaml").read_text())
    cfg["receivers"]["otlp/adk"]["protocols"]["http"]["endpoint"] = f"127.0.0.1:{port}"
    cfg["exporters"]["otlp_http/futureagi"]["traces_endpoint"] = (
        f"http://127.0.0.1:{sink.server_port}/tracer/v1/traces"
    )
    config = a.EVIDENCE / f"customer-v{major}.yaml"
    config.write_text(yaml.safe_dump(cfg, sort_keys=False))
    with (a.EVIDENCE / f"customer-v{major}.collector.log").open("w") as log:
        proc = subprocess.Popen(
            [str(a.COLLECTOR), "--config=" + str(config)],
            env=a.ENV,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    assert time.monotonic() < deadline and proc.poll() is None
                    threading.Event().wait(0.05)
            env = dict(
                a.ENV,
                GOOGLE_API_KEY="synthetic-google-key",
                GOOGLE_MODEL="gemini-test",
                GOOGLE_GEMINI_BASE_URL=f"http://127.0.0.1:{gemini.server_port}",
                OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=f"http://127.0.0.1:{port}/v1/traces",
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="false",
            )
            app = subprocess.run(
                [str(ROOT / f"tests/customer-v{major}/probe")],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert app.returncode == 0, app.stderr
            assert "24 NOTEBOOK-A5" in app.stdout, app.stdout
            assert len(requests) == 2
            assert all(
                r["path"].endswith("models/gemini-test:generateContent")
                for r in requests
            )
            proc.terminate()
            proc.wait(timeout=12)
            combined = a.ExportTraceServiceRequest()
            for row in outgoing:
                request = a.ExportTraceServiceRequest.FromString(row["body"])
                combined.resource_spans.extend(request.resource_spans)
            (a.EVIDENCE / f"customer-v{major}.pb").write_bytes(
                combined.SerializeToString()
            )
            spans = a.decode(outgoing)
            assert len(spans) == (5 if major == "2-latest" else 4)
            assert len({s["trace"] for s in spans}) == 1
            a.assert_complete_traces(spans)
            assert sorted(s["attrs"]["gen_ai.span.kind"] for s in spans) == (
                ["AGENT", "CHAIN", "LLM", "LLM", "TOOL"]
                if major == "2-latest" else ["AGENT", "LLM", "LLM", "TOOL"]
            )
            assert all(b"NOTEBOOK-A5" not in r["body"] for r in outgoing)
            assert all(r["path"] == "/tracer/v1/traces" for r in outgoing)
            assert all(
                s["attrs"].get("session.id") == "inventory-session-1" for s in spans
            ), "model/tool spans missing session membership"
            session_tokens = sum(
                s["attrs"].get("gen_ai.usage.input_tokens", 0)
                + s["attrs"].get("gen_ai.usage.output_tokens", 0)
                for s in spans
                if s["attrs"].get("session.id") == "inventory-session-1"
            )
            assert session_tokens == 36, "session totals omit model usage"
            for row in outgoing:
                h = {k.lower(): v for k, v in row["headers"].items()}
                assert (
                    h["x-api-key"] == "synthetic-api-key"
                    and h["x-secret-key"] == "synthetic-secret-key"
                )
            result = {
                "major": major,
                "status": "PASS",
                "model_requests": len(requests),
                "spans": spans,
                "stdout": app.stdout,
            }
            (a.EVIDENCE / f"customer-v{major}.json").write_text(
                json.dumps(result, indent=2)
            )
            print(
                json.dumps(
                    {
                        "major": major,
                        "status": "PASS",
                        "model_requests": len(requests),
                        "spans": len(spans),
                    }
                )
            )
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=12)
            gemini.shutdown()
            sink.shutdown()
            gemini.server_close()
            sink.server_close()


if __name__ == "__main__":
    for major in (1, 2, "2-latest"):
        test(major)
