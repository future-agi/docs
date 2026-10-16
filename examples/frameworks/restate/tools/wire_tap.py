#!/usr/bin/env python3
"""OTLP/HTTP wire tap: records what an exporter really sends, optionally forwarding it.

  wire_tap.py --listen 4318 --out wire.jsonl [--forward http://localhost:4319]

Every POST is decoded (protobuf or JSON, gzip-aware) and appended to --out as one JSON
line: path, content type, content encoding, the header NAMES (never values), whether the
two Future AGI key headers were present, and the decoded ExportTraceServiceRequest.
With --forward, the original body and headers are passed on unchanged and the upstream
status is returned to the caller; without it the tap answers 200 itself.

--refuse makes the tap answer 503 to every request (exporter-failure test).
If TAP_EXPECT_API_KEY / TAP_EXPECT_SECRET_KEY are set, each record also says whether the
received key headers equal them ("key_values_match"); the values themselves are never written.
"""
import argparse
import gzip
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.protobuf.json_format import MessageToDict, Parse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

KEY_HEADERS = ("x-api-key", "x-secret-key")
HOP_BY_HOP = {"host", "content-length", "connection", "transfer-encoding"}


def decode(body: bytes, content_type: str, content_encoding: str) -> dict:
    if content_encoding == "gzip":
        body = gzip.decompress(body)
    req = ExportTraceServiceRequest()
    if "json" in (content_type or ""):
        Parse(body.decode(), req)
    else:
        req.ParseFromString(body)
    return MessageToDict(req)


def make_handler(out_path: str, forward: str | None, refuse: bool):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("content-length", 0) or 0))
            names = sorted({k.lower() for k in self.headers.keys()})
            rec = {
                "path": self.path,
                "content_type": self.headers.get("content-type"),
                "content_encoding": self.headers.get("content-encoding"),
                "header_names": names,
                "has_key_headers": all(h in names for h in KEY_HEADERS),
            }
            expected = (os.environ.get("TAP_EXPECT_API_KEY"), os.environ.get("TAP_EXPECT_SECRET_KEY"))
            if all(expected):
                got = (self.headers.get("x-api-key") or "", self.headers.get("x-secret-key") or "")
                rec["key_values_match"] = all(hmac.compare_digest(g, e) for g, e in zip(got, expected))
            try:
                rec["body"] = decode(body, rec["content_type"], rec["content_encoding"])
            except Exception as e:  # noqa: BLE001 - record and keep serving
                rec["decode_error"] = type(e).__name__
            status, payload, ctype = 200, b"", "application/x-protobuf"
            if refuse:
                status = 503
            elif forward:
                fwd = urllib.request.Request(forward.rstrip("/") + self.path, data=body, method="POST")
                for k, v in self.headers.items():
                    if k.lower() not in HOP_BY_HOP:
                        fwd.add_header(k, v)
                try:
                    with urllib.request.urlopen(fwd, timeout=30) as r:
                        status, payload = r.status, r.read()
                        ctype = r.headers.get("content-type", ctype)
                except urllib.error.HTTPError as e:
                    status, payload = e.code, e.read()
                except OSError:
                    status = 502
            rec["status"] = status
            with open(out_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            self.send_response(status)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--forward")
    ap.add_argument("--refuse", action="store_true")
    a = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", a.listen), make_handler(a.out, a.forward, a.refuse))
    print(f"wire tap on 127.0.0.1:{a.listen} -> {a.forward or ('503' if a.refuse else '200')}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
