"""What a real Gravitee 4.12.23 Gateway put on the wire (fixtures captured by capture_fixtures.sh).

Needs opentelemetry-proto only. These pin the facts the page relies on, so a Gravitee upgrade that changes
them shows up as a failing test when the fixtures are re-captured.
"""
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

FIX = Path(__file__).resolve().parent.parent / "fixtures"
MARK = "CAPMARK"          # capture_fixtures.sh puts this in the body, query string and headers of every request


def load(name):
    req = ExportTraceServiceRequest()
    req.ParseFromString((FIX / name).read_bytes())
    return req


def attrs(kvs):
    return {kv.key: next(iter(MessageToDict(kv.value).values()), None) for kv in kvs}


def all_spans(req):
    for rs in req.resource_spans:
        for ss in rs.scope_spans:
            yield from ss.spans


def test_extra_attributes_cannot_carry_project_name():
    # gravitee.yml had extraAttributes: [{project_name: ...}, {project_type: observe}]
    res = attrs(load("gravitee-4.12.23-extra-attributes.pb").resource_spans[0].resource.attributes)
    assert "project_name" not in res and "project_type" not in res
    assert res["project.name"] and res["project.type"] == "observe"   # "_" rewritten to "."


def test_content_off_carries_no_content_and_no_node_identity():
    req = load("gravitee-4.12.23-content-off.pb")
    raw = req.SerializeToString()
    assert MARK.encode() not in raw                   # body, query string, headers: none of it exported
    assert b"@example.com" not in raw
    for rs in req.resource_spans:
        res = attrs(rs.resource.attributes)
        assert res["hostname"] == "[REDACTED]" and res["ip"] == "[REDACTED]"
        assert res["service.name"] == "gio-apim-gateway" and res["gravitee.api.name"]
    spans = list(all_spans(req))
    assert all(not s.events for s in spans)           # verbose off: no span events
    root = [s for s in spans if s.kind == s.SPAN_KIND_SERVER]
    assert root and attrs(root[0].attributes)["http.route"] == "/fi-echo"
    assert attrs(root[0].attributes)["http.target"] == "[REDACTED]"   # it had a query string
    assert not any(k.startswith("gen_ai.") or k.startswith("llm.") for s in spans for k in attrs(s.attributes))


def test_failed_backend_is_error_without_raw_error_text():
    spans = list(all_spans(load("gravitee-4.12.23-backend-down.pb")))
    assert {s.name for s in spans if s.status.code == s.status.STATUS_CODE_ERROR} >= {"GET /fi-down", "endpoint-invoker"}
    events = [e for s in spans for e in s.events]
    assert events and all(attrs(e.attributes).get("exception.message") == "[REDACTED]" for e in events)
    assert all(attrs(e.attributes).get("exception.stacktrace") == "[REDACTED]" for e in events)
    inv = [s for s in spans if s.name == "endpoint-invoker"][0]
    assert attrs(inv.attributes)["gravitee.execution-failure.key"] == "GATEWAY_CLIENT_CONNECTION_REFUSED"


def test_verbose_opt_in_adds_headers_but_masks_credentials():
    req = load("gravitee-4.12.23-verbose.pb")
    events = [attrs(e.attributes) for s in all_spans(req) for e in s.events]
    assert events, "verbose mode should attach gravitee.policy.pre/post events to the policy span"
    hdr = {k.lower(): v for ev in events for k, v in ev.items() if k.lower().startswith("http.request.header.")}
    assert hdr["http.request.header.x-custom"].startswith(MARK)            # the opt-in: header content exported
    for secret in ("authorization", "cookie", "x-gravitee-api-key"):
        assert hdr[f"http.request.header.{secret}"] == "[REDACTED]"
    assert all(v == "[REDACTED]" for ev in events for k, v in ev.items() if k.endswith("original-url"))
