#!/usr/bin/env python3
"""Print an OTLP/HTTP protobuf traces body (ExportTraceServiceRequest) as JSON.

  otlp_dump.py body.bin [body2.bin ...]

Used to inspect what the Gateway exported (resource attributes, span names,
attributes, events, status) and by the tests to read the captured fixtures.
"""
import json
import sys

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


def load(path):
    req = ExportTraceServiceRequest()
    with open(path, "rb") as f:
        req.ParseFromString(f.read())
    return req


def attrs(kvs):
    out = {}
    for kv in kvs:
        v = MessageToDict(kv.value)
        out[kv.key] = next(iter(v.values())) if v else None
    return out


def summarize(req):
    rs_out = []
    for rs in req.resource_spans:
        spans = []
        for ss in rs.scope_spans:
            for s in ss.spans:
                spans.append({
                    "name": s.name, "trace_id": s.trace_id.hex(), "span_id": s.span_id.hex(),
                    "parent_span_id": s.parent_span_id.hex(), "kind": s.kind,
                    "status": {"code": s.status.code, "message": s.status.message},
                    "attributes": attrs(s.attributes),
                    "events": [{"name": e.name, "attributes": attrs(e.attributes)} for e in s.events],
                    "scope": ss.scope.name,
                })
        rs_out.append({"resource": attrs(rs.resource.attributes), "spans": spans})
    return rs_out


if __name__ == "__main__":
    print(json.dumps([summarize(load(p)) for p in sys.argv[1:]], indent=1))
