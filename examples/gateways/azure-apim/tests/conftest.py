"""Fixtures: a recording stand-in for the Future AGI collector, a tiny OpenAI-compatible model stub, the APIM stand-in,
and a runner that launches ../app.py as a separate process, as a customer would."""
import gzip
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import apim_standin  # noqa: E402

GW_FI_KEY = "gw-fi-api-key-0001"
GW_FI_SECRET = "gw-fi-secret-key-0002"
SUB_KEY = "sub-key-0003"
LLM_KEY = "llm-key-0004"
MODEL = "example-model"


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Recorder:
    """Plays fi-collector: records every request and answers 200, like a collector that accepted the batch."""

    def __init__(self, status=200):
        self.requests, self.status, rec = [], status, self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                rec.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                out = trace_service_pb2.ExportTraceServiceResponse().SerializeToString() if rec.status == 200 else b'{"error":"x"}'
                self.send_response(rec.status)
                self.send_header("Content-Type", "application/x-protobuf" if rec.status == 200 else "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = _serve(H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def spans(self):
        found = []
        for r in self.requests:
            body = gzip.decompress(r["body"]) if r["headers"].get("content-encoding") == "gzip" else r["body"]
            msg = trace_service_pb2.ExportTraceServiceRequest()
            msg.ParseFromString(body)
            for rs in MessageToDict(msg, preserving_proto_field_name=True).get("resource_spans", []):
                res = {a["key"]: next(iter(a["value"].values())) for a in rs.get("resource", {}).get("attributes", [])}
                for ss in rs.get("scope_spans", []):
                    for sp in ss.get("spans", []):
                        sp["_resource"] = res
                        sp["_attrs"] = {a["key"]: next(iter(a["value"].values())) for a in sp.get("attributes", [])}
                        found.append(sp)
        return found

    def raw(self):
        return b"\n".join(r["body"] for r in self.requests)


def make_llm_stub():
    """OpenAI-compatible Chat Completions: echoes the last user text; forces one tool call; 401 on a wrong key."""

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.headers.get("Authorization") != f"Bearer {LLM_KEY}":
                out, status = {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}}, 401
            else:
                status = 200
                msgs = req.get("messages", [])
                last_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
                if req.get("tools") and msgs[-1]["role"] == "user":
                    msg = {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "lookup_record", "arguments": json.dumps({"query": last_user})}}]}
                elif msgs[-1]["role"] == "tool":
                    msg = {"role": "assistant", "content": f"answer: {msgs[-1]['content']}"}
                else:
                    msg = {"role": "assistant", "content": f"echo: {last_user}"}
                out = {"id": "c1", "object": "chat.completion", "created": 1, "model": req.get("model", MODEL),
                       "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if msg.get("tool_calls") else "stop"}],
                       "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}
            data = json.dumps(out).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = _serve(H)
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


@pytest.fixture
def backend():
    rec = Recorder()
    yield rec
    rec.server.shutdown()


@pytest.fixture
def apim(backend):
    server = apim_standin.serve(backend.url + "/tracer/v1/traces", 0, SUB_KEY, GW_FI_KEY, GW_FI_SECRET)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    server.shutdown()


@pytest.fixture
def llm():
    server, url = make_llm_stub()
    yield url
    server.shutdown()


@pytest.fixture
def run_app(apim, llm):
    def run(*args, env=None, drop=()):
        e = {k: v for k, v in os.environ.items() if not k.startswith("FI_") and k not in drop}
        e.update(FI_BASE_URL=apim.url, FI_PROJECT_NAME="proj-test", APIM_SUBSCRIPTION_KEY=SUB_KEY,
                 LLM_BASE_URL=llm, LLM_API_KEY=LLM_KEY, LLM_MODEL=MODEL, OTEL_BSP_SCHEDULE_DELAY="200")
        e.update(env or {})
        return subprocess.run([sys.executable, str(ROOT / "app.py"), *args], capture_output=True, text=True, env=e, timeout=90)
    return run
