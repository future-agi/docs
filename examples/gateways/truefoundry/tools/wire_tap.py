#!/usr/bin/env python3
"""Record what an OTLP/HTTP exporter puts on the wire, then forward it unchanged.

Point an exporter at this tap instead of the collector to see exactly what
leaves the process before Future AGI stores anything. Request bodies are decoded
(protobuf or JSON) and appended, one JSON object per request, to the output
file. Header values for credentials are replaced with <redacted>.

  wire_tap.py --listen 18305 --forward http://localhost:14338 --out wire.jsonl

Needs: pip install opentelemetry-proto
The output contains whatever the exporter sent, prompts included when content
capture is on. Keep it out of version control.
"""
import argparse
import gzip
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

SECRET_HEADERS = {"x-api-key", "x-secret-key", "authorization", "api_key", "space_id"}
args = None


def decode(body: bytes, content_type: str, encoding: str):
    raw = gzip.decompress(body) if encoding.lower() == "gzip" else body
    if content_type.startswith("application/x-protobuf"):
        msg = ExportTraceServiceRequest()
        msg.ParseFromString(raw)
        return MessageToDict(msg)
    return json.loads(raw)


class Tap(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        sys.stderr.write("wire-tap: %s\n" % (fmt % a))

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        ctype = self.headers.get("Content-Type", "")
        enc = self.headers.get("Content-Encoding", "")
        record = {
            "path": self.path,
            "content_type": ctype,
            "content_encoding": enc or None,
            "bytes": len(body),
            "headers": {
                k.lower(): ("<redacted>" if k.lower() in SECRET_HEADERS else v)
                for k, v in self.headers.items()
                if k.lower() not in {"host", "content-length", "connection", "accept-encoding"}
            },
        }
        try:
            record["body"] = decode(body, ctype, enc)
        except Exception as exc:
            record["decode_error"] = type(exc).__name__
        with open(args.out, "a") as f:
            f.write(json.dumps(record) + "\n")

        fwd_headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length", "connection"}}
        req = urllib.request.Request(args.forward.rstrip("/") + self.path, data=body, method="POST", headers=fwd_headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                status, payload, rctype = resp.status, resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            status, payload, rctype = exc.code, exc.read(), exc.headers.get("Content-Type", "")
        self.send_response(status)
        if rctype:
            self.send_header("Content-Type", rctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    global args
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=18305)
    ap.add_argument("--forward", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.listen), Tap)
    print(f"wire tap on http://127.0.0.1:{args.listen} -> {args.forward}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
