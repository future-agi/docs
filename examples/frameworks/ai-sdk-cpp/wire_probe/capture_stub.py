#!/usr/bin/env python3
"""Loopback stand-in for a Langfuse host. Records every POST to a JSONL file and answers 207.

usage: capture_stub.py <out.jsonl> <port>

Each line: ts, method, path, headers (Authorization value redacted), basic_auth_user, content_type, body.
Binds to 127.0.0.1 only. The keys it sees are the probe's fake ones; the Authorization value is not stored.
"""
import base64
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def make_server(out_path, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                body = json.loads(raw)
            except ValueError:
                body = {"_unparsed_bytes": len(raw)}
            auth = self.headers.get("Authorization", "")
            user = ""
            if auth.startswith("Basic "):
                try:
                    user = base64.b64decode(auth[6:]).decode().split(":")[0]
                except Exception:
                    pass
            record = {
                "ts": time.time(),
                "method": "POST",
                "path": self.path,
                "headers": {k: ("<redacted>" if k.lower() == "authorization" else v) for k, v in self.headers.items()},
                "basic_auth_user": user,
                "content_type": self.headers.get("Content-Type"),
                "body": body,
            }
            with open(out_path, "a") as f:
                f.write(json.dumps(record) + "\n")
            payload = json.dumps({"successes": [], "errors": []}).encode()
            self.send_response(207)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return HTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    make_server(sys.argv[1], int(sys.argv[2])).serve_forever()
