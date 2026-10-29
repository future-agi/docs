#!/usr/bin/env python3
"""POST a synthetic TrueFoundry-shaped OTLP batch to an OTLP receiver.

Plays the part of the gateway's OTEL exporter for tests. It is NOT TrueFoundry code.

  FI_API_KEY=... FI_SECRET_KEY=... post_batch.py --url http://localhost:14338/v1/traces \\
      --resource project_name=my-project --resource project_type=observe

Auth modes (--auth):
  headers   X-Api-Key and X-Secret-Key, two header pairs (default)
  basic     one Authorization header: Basic base64(api_key:secret_key)
  bearer    Authorization: Bearer <api_key>  (the collector rejects this; shown as the negative case)
  wrong     X-Api-Key and X-Secret-Key that belong to no account (negative case)
  none      no credentials

Prints the HTTP status, the response body head, and the trace id. Never prints keys.
"""
import argparse
import base64
import gzip
import json
import os
import sys
import urllib.error
import urllib.request

from google.protobuf.json_format import MessageToJson

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tfy_batch import build_batch  # noqa: E402


def auth_headers(mode: str) -> dict:
    key, secret = os.environ.get("FI_API_KEY", ""), os.environ.get("FI_SECRET_KEY", "")
    if mode == "headers":
        return {"X-Api-Key": key, "X-Secret-Key": secret}
    if mode == "basic":
        return {"Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode()}
    if mode == "bearer":
        return {"Authorization": f"Bearer {key}"}
    if mode == "wrong":
        return {"X-Api-Key": "not-a-real-key", "X-Secret-Key": "not-a-real-secret"}
    return {}


def to_otlp_json(req) -> bytes:
    """OTLP/JSON, per the spec: trace and span ids are hex strings, not base64."""
    doc = json.loads(MessageToJson(req))

    def fix(node):
        if isinstance(node, dict):
            for key in ("traceId", "spanId", "parentSpanId"):
                if isinstance(node.get(key), str) and node[key]:
                    node[key] = base64.b64decode(node[key]).hex()
            for value in node.values():
                fix(value)
        elif isinstance(node, list):
            for value in node:
                fix(value)

    fix(doc)
    return json.dumps(doc).encode()


def post_http(url: str, req, *, encoding: str, headers: dict, gzip_body: bool, timeout: float = 30.0):
    if encoding == "json":
        body, ctype = to_otlp_json(req), "application/json"
    else:
        body, ctype = req.SerializeToString(), "application/x-protobuf"
    hdrs = {"Content-Type": ctype, **headers}
    if gzip_body:
        body, hdrs["Content-Encoding"] = gzip.compress(body), "gzip"
    request = urllib.request.Request(url, data=body, method="POST", headers=hdrs)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def post_grpc(target: str, req, *, headers: dict, insecure: bool = True):
    import grpc
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc

    channel = grpc.insecure_channel(target) if insecure else grpc.secure_channel(target, grpc.ssl_channel_credentials())
    stub = trace_service_pb2_grpc.TraceServiceStub(channel)
    metadata = [(k.lower(), v) for k, v in headers.items()]  # gRPC metadata keys are lowercase
    try:
        stub.Export(req, metadata=metadata, timeout=30)
        return "OK", b""
    except grpc.RpcError as exc:
        return exc.code().name, (exc.details() or "").encode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="OTLP/HTTP traces URL, including the path")
    ap.add_argument("--grpc", help="host:port of an OTLP/gRPC receiver (plaintext)")
    ap.add_argument("--encoding", choices=["proto", "json"], default="proto")
    ap.add_argument("--auth", choices=["headers", "basic", "bearer", "wrong", "none"], default="headers")
    ap.add_argument("--gzip", action="store_true", help="gzip the request body")
    ap.add_argument("--marker", default="MARKER")
    ap.add_argument("--genai", choices=["on", "off"], default="on")
    ap.add_argument("--content", choices=["on", "exclude_literal", "off"], default="on")
    ap.add_argument("--failure", action="store_true")
    ap.add_argument("--no-error-status", action="store_true", help="with --failure: leave the OTLP status unset")
    ap.add_argument("--exception-event", action="store_true", help="with --failure: add a synthetic exception event")
    ap.add_argument("--resource", action="append", default=[], help="KEY=VALUE resource attribute (repeatable)")
    a = ap.parse_args()
    if bool(a.url) == bool(a.grpc):
        ap.error("give exactly one of --url or --grpc")
    resource = dict(r.split("=", 1) for r in a.resource)
    req = build_batch(
        a.marker,
        genai=a.genai == "on",
        content=a.content,
        failure=a.failure,
        error_status=not a.no_error_status,
        exception_event=a.exception_event,
        resource_attrs=resource,
    )
    tid = req.resource_spans[0].scope_spans[0].spans[0].trace_id.hex()
    headers = auth_headers(a.auth)
    if a.url:
        status, body = post_http(a.url, req, encoding=a.encoding, headers=headers, gzip_body=a.gzip)
    else:
        status, body = post_grpc(a.grpc, req, headers=headers)
    print(f"status={status} trace_id={tid} body={body[:120]!r}")
    return 0 if str(status) in ("200", "OK") else 1


if __name__ == "__main__":
    sys.exit(main())
