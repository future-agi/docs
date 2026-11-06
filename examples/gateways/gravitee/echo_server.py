#!/usr/bin/env python3
"""Tiny HTTP backend for the Gravitee API used in run_e2e.sh.

Answers every request with a short fixed JSON body. It does not echo the request
back. It appends one line per request (method, path, whether a W3C traceparent
arrived, and its trace id) to --log so the run can check that Gravitee forwards
trace context to the backend. Request bodies and header values are not logged.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=18090)
ap.add_argument("--bind", default="0.0.0.0")
ap.add_argument("--log", required=True)
args = ap.parse_args()


class H(BaseHTTPRequestHandler):
    def _answer(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        tp = self.headers.get("traceparent") or ""
        with open(args.log, "a") as f:
            f.write(json.dumps({"method": self.command, "path": self.path.split("?")[0],
                                "traceparent_trace_id": tp.split("-")[1] if tp.count("-") == 3 else None}) + "\n")
        body = b'{"ok":true,"backend":"echo"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = _answer

    def log_message(self, *a):
        pass


ThreadingHTTPServer((args.bind, args.port), H).serve_forever()
