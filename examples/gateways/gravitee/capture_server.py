#!/usr/bin/env python3
"""Tiny OTLP/HTTP sink. Saves each POST body (raw bytes, as sent) to --out-dir.

Used only to capture what a real Gravitee gateway sends, so the bytes can be
inspected and replayed against Future AGI in tests. Header NAMES, the request
path, Content-Type and Content-Encoding are written next to each body; header
values (the Future AGI keys) are never written. Bind it to a private address.
"""
import argparse
import itertools
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=18318)
ap.add_argument("--bind", default="0.0.0.0")
ap.add_argument("--out-dir", required=True)
args = ap.parse_args()
os.makedirs(args.out_dir, exist_ok=True)
counter = itertools.count(1)
SAFE = {"content-type", "content-encoding", "user-agent"}


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        n = next(counter)
        with open(os.path.join(args.out_dir, f"{n:03d}.bin"), "wb") as f:
            f.write(body)
        with open(os.path.join(args.out_dir, f"{n:03d}.meta"), "w") as f:
            f.write("path=" + self.path + "\n")
            for k, v in self.headers.items():
                if k.lower() in SAFE:
                    f.write(f"{k}={v}\n")
                elif v.startswith("${"):
                    f.write(f"{k}=<unresolved placeholder>\n")   # a config placeholder was sent literally
                else:
                    f.write(f"{k}=<value not recorded, {len(v)} chars>\n")
        self.send_response(200)
        self.send_header("Content-Type", self.headers.get("Content-Type", "application/x-protobuf"))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


ThreadingHTTPServer((args.bind, args.port), H).serve_forever()
