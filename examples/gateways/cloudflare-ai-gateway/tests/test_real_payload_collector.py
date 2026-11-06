"""Real Cloudflare AI Gateway payloads through the real collector running otelcol.yaml.

tests/fixtures/cloudflare-2026-10-18-*.json are what a real gateway (OpenAI behind it) exported on 2026-10-18,
read back from the collector it posted to. The prompts are synthetic marker text. Each test posts one of them
to otelcol-contrib 0.162.0 in Docker and decodes what the collector forwards to a local stand-in for Future AGI.

Skipped without Docker or without the image (`docker pull otel/opentelemetry-collector-contrib:0.162.0`), or with
CFAIG_SKIP_DOCKER=1.
"""
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import gateway_fixture as gf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(HERE, "tests", "fixtures")
IMAGE = "otel/opentelemetry-collector-contrib:0.162.0"


def docker_ready():
    if os.environ.get("CFAIG_SKIP_DOCKER") == "1" or not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not docker_ready(), reason=f"needs Docker and the {IMAGE} image")


def load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def attrs(kvs):
    return {a.key: getattr(a.value, a.value.WhichOneof("value")) for a in kvs}


class Sink:
    """Stands in for the Future AGI traces endpoint: records decoded exports and the headers they came with."""

    def __init__(self):
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

        self.seen = []
        sink = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):  # noqa: N802
                msg = ExportTraceServiceRequest()
                msg.ParseFromString(self.rfile.read(int(self.headers["Content-Length"])))
                sink.seen.append({"headers": dict(self.headers), "msg": msg})
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.srv = HTTPServer(("0.0.0.0", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def spans(self, trace_hex, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for s in self.seen:
                for rs in s["msg"].resource_spans:
                    for ss in rs.scope_spans:
                        for sp in ss.spans:
                            if sp.trace_id.hex() == trace_hex:
                                return s, rs, ss, sp
            time.sleep(0.3)
        raise AssertionError(f"collector forwarded nothing for {trace_hex}")


@pytest.fixture(scope="module", params=["false", "true"], ids=["content-off", "content-on"])
def collector(request):
    sink = Sink()
    token = secrets.token_hex(16)
    name = f"cfaig-test-{secrets.token_hex(4)}"
    env = dict(os.environ, GATEWAY_TOKEN=token)
    run = subprocess.run([
        "docker", "run", "-d", "--rm", "--name", name, "--memory", "384m", "--add-host=host.docker.internal:host-gateway",
        "-p", "127.0.0.1::4318", "-v", f"{os.path.join(HERE, 'otelcol.yaml')}:/etc/otelcol/config.yaml:ro",
        "-e", "GATEWAY_TOKEN", "-e", "FI_API_KEY=test-key", "-e", "FI_SECRET_KEY=test-secret",
        "-e", "FI_PROJECT_NAME=cf-test", "-e", f"FI_CAPTURE_CONTENT={request.param}",
        "-e", f"FI_TRACES_URL=http://host.docker.internal:{sink.srv.server_port}/v1/traces",
        IMAGE, "--config", "/etc/otelcol/config.yaml"], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    try:
        port = subprocess.run(["docker", "port", name, "4318/tcp"], capture_output=True, text=True).stdout.split(":")[-1].strip()
        url = f"http://127.0.0.1:{port}/v1/traces"
        for _ in range(60):
            try:
                urllib.request.urlopen(urllib.request.Request(url, data=b"{}", method="POST"), timeout=2)
            except urllib.error.HTTPError:
                break          # 401 without the token: the receiver is up
            except OSError:
                time.sleep(0.5)
        yield {"url": url, "token": token, "sink": sink, "capture": request.param == "true"}
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        sink.srv.shutdown()


def post(c, body, content_type="json"):
    data = gf.to_protobuf(body) if content_type == "protobuf" else json.dumps(body).encode()
    ctype = "application/x-protobuf" if content_type == "protobuf" else "application/json"
    req = urllib.request.Request(c["url"], data=data, method="POST",
                                 headers={"Content-Type": ctype, "Authorization": f"Bearer {c['token']}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200


def original(body, key):
    sp = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    return next(a["value"]["stringValue"] for a in sp["attributes"] if a["key"] == key)


@pytest.mark.parametrize("fixture,content_type", [
    ("cloudflare-2026-10-18-chat.json", "json"),
    ("cloudflare-2026-10-18-chat.json", "protobuf"),
    ("cloudflare-2026-10-18-stream.json", "json"),
])
def test_real_gateway_span_reaches_future_agi_in_the_right_shape(collector, fixture, content_type):
    body = load(fixture)
    sp_in = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    # a fresh trace id per post, so the content-off and content-on legs and the two encodings do not mix
    sp_in["traceId"] = secrets.token_hex(16)
    post(collector, body, content_type)
    export, rs, ss, sp = collector["sink"].spans(sp_in["traceId"])

    assert export["headers"].get("X-Api-Key") == "test-key" and export["headers"].get("X-Secret-Key") == "test-secret"
    assert "gzip" not in export["headers"].get("Content-Encoding", "")
    res = attrs(rs.resource.attributes)
    assert res["project_name"] == "cf-test" and res["project_type"] == "observe" and res["service.name"] == "ai-gateway"
    assert sp.name == "cf.aig.request" and ss.scope.name == "ai"

    a = attrs(sp.attributes)
    assert a["fi.span.kind"] == "LLM"
    assert a["gen_ai.provider.name"] == "openai" and a["gen_ai.request.model"].startswith("gpt-4o-mini")
    assert a["gen_ai.usage.input_tokens"] > 0 and a["gen_ai.usage.output_tokens"] > 0
    assert a["gen_ai.cost.total"] == a["gen_ai.usage.cost"] > 0
    assert a["team"] == "th8103"                                    # cf-aig-metadata, kept in both modes
    assert "gen_ai.input.messages" not in a and "gen_ai.output.messages" not in a   # never stored twice

    wire = export["msg"].SerializeToString()
    if collector["capture"]:
        assert a["input.value"] == original(body, "gen_ai.input.messages")
        assert a["output.value"] == original(body, "gen_ai.output.messages")
        assert a["input.mime_type"] == a["output.mime_type"] == "application/json"
    else:
        assert "input.value" not in a and "output.value" not in a and "input.mime_type" not in a
        for needle in (b"Reply with exactly", b"chatcmpl-", b"OK CFLIVE"):
            assert needle not in wire, needle


def test_documented_attribute_names_are_handled_too(collector):
    r = gf.GatewayRequest(doc_names=True, prompt=[{"role": "user", "content": "DOCNAMES-marker"}],
                          completion={"role": "assistant", "content": "DOCNAMES-reply"})
    body = gf.build_request(r)
    tid = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    post(collector, body)
    export, _, _, sp = collector["sink"].spans(tid)
    a = attrs(sp.attributes)
    assert a["gen_ai.provider.name"] == a["gen_ai.model.provider"] == "openai"
    assert "gen_ai.prompt_json" not in a and "gen_ai.completion_json" not in a
    if collector["capture"]:
        assert "DOCNAMES-marker" in a["input.value"] and "DOCNAMES-reply" in a["output.value"]
    else:
        assert b"DOCNAMES" not in export["msg"].SerializeToString()
