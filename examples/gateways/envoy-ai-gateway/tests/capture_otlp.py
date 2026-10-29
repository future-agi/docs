#!/usr/bin/env python3
"""Tiny OTLP/HTTP trace capture server used to record contract fixtures from a real aigw run.

usage: capture_otlp.py <port> <out.json>     (needs `pip install opentelemetry-proto`)
Writes every received ExportTraceServiceRequest (decoded to JSON) plus the request headers' names
and the sanitised auth header presence to <out.json> on SIGTERM/SIGINT. Header VALUES are never stored.
"""
import json, signal, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

captured = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        entry = {"path": self.path, "content_type": self.headers.get("content-type"),
                 "content_encoding": self.headers.get("content-encoding"),
                 "header_names": sorted(k.lower() for k in self.headers.keys())}
        if self.path.endswith("/v1/traces"):
            req = ExportTraceServiceRequest()
            req.ParseFromString(body)
            entry["request"] = MessageToDict(req)
        captured.append(entry)
        self.send_response(200); self.send_header("content-type", "application/x-protobuf"); self.end_headers()

    def log_message(self, *a):
        pass


def main():
    port, out = int(sys.argv[1]), sys.argv[2]
    srv = HTTPServer(("127.0.0.1", port), H)

    def stop(*_):
        json.dump(captured, open(out, "w"), indent=1)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    srv.serve_forever()


if __name__ == "__main__":
    main()
