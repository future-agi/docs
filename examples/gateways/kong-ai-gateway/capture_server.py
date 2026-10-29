#!/usr/bin/env python3
"""Tiny OTLP/HTTP sink. Saves each POST /v1/traces body (raw protobuf) to --out-dir.

Used only to capture what a real Kong gateway sends, so the bytes can be replayed
against Future AGI. Never exposed publicly; binds to the address you give it.
"""
import argparse
import itertools
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=18318)
ap.add_argument("--bind", default="0.0.0.0")
ap.add_argument("--out-dir", required=True)
args = ap.parse_args()
os.makedirs(args.out_dir, exist_ok=True)
counter = itertools.count(1)


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        n = next(counter)
        with open(os.path.join(args.out_dir, f"{n:03d}.pb"), "wb") as f:
            f.write(body)
        with open(os.path.join(args.out_dir, f"{n:03d}.headers"), "w") as f:
            # header NAMES only; values (auth) are never written
            f.write("\n".join(f"{k}" for k in self.headers.keys()) + "\n")
            f.write("path=" + self.path + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


HTTPServer((args.bind, args.port), H).serve_forever()
