"""The drain-shaped fixture and its replay script. No Vercel call, no collector needed."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

import replay_drain

# Attribute names Vercel publishes (https://vercel.com/docs/ai-gateway/observability-and-spend/trace-drains,
# last updated 2026-09-08, read 2026-10-15). The fixture may use these and nothing else.
PUBLISHED = {
    "gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.response.model",
    "gen_ai.response.finish_reasons", "gen_ai.request.stream", "gen_ai.response.time_to_first_chunk",
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.usage.reasoning.output_tokens",
    "gen_ai.usage.cache_creation.input_tokens", "gen_ai.usage.cache_read.input_tokens", "http.response.status_code",
    "vercel.ai_gateway.provider", "vercel.ai_gateway.request.id", "vercel.ai_gateway.generation.id",
    "vercel.ai_gateway.api_key.id", "vercel.ai_gateway.api_key.name", "vercel.ai_gateway.api_format",
    "vercel.ai_gateway.credential.type", "vercel.ai_gateway.byok.credential.id", "vercel.ai_gateway.cost.total",
    "vercel.ai_gateway.cost.currency", "vercel.ai_gateway.cost.market", "vercel.ai_gateway.cost.market_currency",
    "vercel.ai_gateway.zdr.requested", "vercel.ai_gateway.service_tier", "vercel.ai_gateway.referring_site.url",
    "vercel.ai_gateway.referring_site.name", "vercel.ai_gateway.tags", "vercel.ai_gateway.environment",
    "vercel.ai_gateway.region", "vercel.ai_gateway.user.id", "vercel.project.id", "vercel.deployment.id",
    "vercel.ai_gateway.vmc.id", "vercel.ai_gateway.vmc.used", "vercel.ai_gateway.routing.provider_only_filter",
    "vercel.ai_gateway.routing.custom_provider_order", "vercel.ai_gateway.model_attempt.index",
    "vercel.ai_gateway.model_attempt.total", "vercel.ai_gateway.model_attempt.is_last",
    "vercel.ai_gateway.model_attempt.success", "vercel.ai_gateway.model_attempt.provider_attempt_count",
    "error.type", "vercel.ai_gateway.attempt.id", "vercel.ai_gateway.attempt.number",
    "vercel.ai_gateway.attempt.total_in_request", "vercel.ai_gateway.attempt.total_in_model_attempt",
    "vercel.ai_gateway.attempt.is_final", "vercel.ai_gateway.attempt.success",
    "vercel.ai_gateway.attempt.provider_timeout", "vercel.ai_gateway.attempt.configured_timeout_ms",
    "vercel.ai_gateway.attempt.provider_request_id", "vercel.ai_gateway.attempt.provider_response_id",
}
CONTENT_WORDS = ("prompt", "completion", "message", "input.value", "output.value", "instruction", "content")


@pytest.fixture()
def fixture():
    return replay_drain.load_fixture()


def spans_of(payload):
    return [sp for rs in payload["resourceSpans"] for ss in rs["scopeSpans"] for sp in ss["spans"]]


def attr_map(attrs):
    return {a["key"]: a["value"] for a in attrs}


def test_resource_attributes_are_the_two_fixed_ones_and_no_project(fixture):
    (rs,) = fixture["resourceSpans"]
    assert {k: v["stringValue"] for k, v in attr_map(rs["resource"]["attributes"]).items()} == {
        "service.name": "ai-gateway",
        "service.namespace": "vercel",
    }


def test_fixture_uses_only_published_attribute_names(fixture):
    used = {a["key"] for sp in spans_of(fixture) for a in sp["attributes"]}
    assert used <= PUBLISHED, sorted(used - PUBLISHED)


def test_fixture_has_the_four_documented_span_shapes(fixture):
    names = [sp["name"] for sp in spans_of(fixture)]
    assert names[0].startswith("chat ")
    assert names[1] == "vercel.ai_gateway.routing"
    assert names[2].startswith("vercel.ai_gateway.model_attempt ")
    assert names[3].endswith(" (example-provider)")
    parents = {sp["spanId"]: sp.get("parentSpanId") for sp in spans_of(fixture)}
    root = spans_of(fixture)[0]["spanId"]
    assert parents[root] is None and sum(1 for p in parents.values() if p is None) == 1


def test_fixture_carries_no_prompt_or_completion_content(fixture):
    for sp in spans_of(fixture):
        assert not sp.get("events")
        for key in (a["key"] for a in sp["attributes"]):
            assert not any(word in key for word in CONTENT_WORDS), key
    assert "example" in json.dumps(fixture)  # values are placeholders, not captures


def test_with_project_name_adds_the_attribute_a_drain_cannot_set(fixture):
    stamped = replay_drain.with_project_name(fixture, "my-project", "observe")
    attrs = attr_map(stamped["resourceSpans"][0]["resource"]["attributes"])
    assert attrs["project_name"] == {"stringValue": "my-project"} and attrs["project_type"] == {"stringValue": "observe"}
    assert "project_name" not in attr_map(fixture["resourceSpans"][0]["resource"]["attributes"])


def test_fresh_ids_make_a_new_trace_and_keep_the_tree(fixture):
    fresh = replay_drain.fresh_ids(fixture, now_ns=1_800_000_000_000_000_000)
    old, new = spans_of(fixture), spans_of(fresh)
    assert {sp["traceId"] for sp in new} != {sp["traceId"] for sp in old} and len({sp["traceId"] for sp in new}) == 1
    assert all(len(sp["traceId"]) == 32 and len(sp["spanId"]) == 16 for sp in new)
    index = {o["spanId"]: n["spanId"] for o, n in zip(old, new)}
    for o, n in zip(old, new):
        assert (n.get("parentSpanId") is None) == (o.get("parentSpanId") is None)
        if o.get("parentSpanId"):
            assert n["parentSpanId"] == index[o["parentSpanId"]]
    assert int(new[0]["startTimeUnixNano"]) < 1_800_000_000_000_000_000


@pytest.mark.parametrize("fmt", ["json", "protobuf"])
def test_both_drain_formats_encode_the_same_trace(fixture, fmt):
    body, ctype = replay_drain.encode(fixture, fmt)
    if fmt == "json":
        assert ctype == "application/json" and json.loads(body) == fixture
        return
    assert ctype == "application/x-protobuf"
    msg = trace_service_pb2.ExportTraceServiceRequest()
    msg.ParseFromString(body)
    first = msg.resource_spans[0].scope_spans[0].spans[0]
    assert first.trace_id.hex() == fixture["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    assert len(msg.resource_spans[0].scope_spans[0].spans) == 4
    names = [a.key for a in msg.resource_spans[0].resource.attributes]
    assert names == ["service.name", "service.namespace"]


class Recorder:
    def __init__(self):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.requests.append({"headers": {k.lower(): v for k, v in self.headers.items()}, "body": body, "path": self.path})
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/traces"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture()
def recorder(monkeypatch):
    monkeypatch.setenv("FI_API_KEY", "k-api")
    monkeypatch.setenv("FI_SECRET_KEY", "k-secret")
    r = Recorder()
    yield r
    r.server.shutdown()


def test_replay_sends_the_key_pair_headers_and_no_project_by_default(recorder, capsys):
    assert replay_drain.main(["--endpoint", recorder.url]) == 0
    (req,) = recorder.requests
    assert req["headers"]["x-api-key"] == "k-api" and req["headers"]["x-secret-key"] == "k-secret"
    assert "authorization" not in req["headers"]
    assert b"project_name" not in req["body"]


def test_replay_with_project_name_in_protobuf(recorder):
    assert replay_drain.main(["--endpoint", recorder.url, "--format", "protobuf", "--project-name", "p1"]) == 0
    (req,) = recorder.requests
    assert req["headers"]["content-type"] == "application/x-protobuf"
    msg = trace_service_pb2.ExportTraceServiceRequest()
    msg.ParseFromString(req["body"])
    assert "project_name" in {a.key for a in msg.resource_spans[0].resource.attributes}
    assert MessageToDict(msg)["resourceSpans"]


def test_bearer_mode_sends_only_an_authorization_header(recorder):
    replay_drain.main(["--endpoint", recorder.url, "--auth", "bearer"])
    (req,) = recorder.requests
    assert req["headers"]["authorization"] == "Bearer k-api" and "x-api-key" not in req["headers"]


def test_gzip_mode_marks_the_body(recorder):
    replay_drain.main(["--endpoint", recorder.url, "--gzip"])
    (req,) = recorder.requests
    assert req["headers"]["content-encoding"] == "gzip" and req["body"][:2] == b"\x1f\x8b"


def test_kind_styles_cover_the_vercel_reference_example(fixture):
    doc = replay_drain.set_kind_style(fixture, "doc-example")
    assert [sp["kind"] for sp in spans_of(doc)] == ["server", "internal", "internal", "client"]
    assert [sp["kind"] for sp in spans_of(replay_drain.set_kind_style(fixture, "enum"))][0] == "SPAN_KIND_SERVER"
