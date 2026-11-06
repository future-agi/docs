#!/usr/bin/env python3
"""Record what an OTLP/HTTP exporter really sends, so you can check it before pointing it at Future AGI.

Point ``OTEL_ENDPOINT`` at this sink instead of Future AGI and every request is written to
``--out`` as ``NNN-<signal>.json`` (OTLP/JSON, decoded from protobuf when needed) next to a
``requests.jsonl`` log holding the request path, content type, content encoding, size and which
Future AGI auth headers were present (never their values). Use it to prove that the proxy sends
only ``/v1/traces``, uncompressed, with the headers and resource attributes you expect.

Needs ``opentelemetry-proto`` (installed with ``opentelemetry-exporter-otlp``) to decode protobuf;
OTLP/JSON bodies need nothing.

Usage:  python3 otlp_sink.py --port 14390 --out ./captures
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AUTH_HEADERS = ("x-api-key", "x-secret-key", "authorization")


def decode_traces(body: bytes, content_type: str) -> dict:
    """OTLP traces body -> OTLP/JSON dict."""
    if "json" in content_type:
        return json.loads(body or b"{}")
    from google.protobuf.json_format import MessageToDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    message = ExportTraceServiceRequest()
    message.ParseFromString(body)
    return MessageToDict(message)


class Sink:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.count = 0
        self.log = self.out / "requests.jsonl"

    def record(self, path: str, headers: dict, body: bytes) -> None:
        content_type = headers.get("content-type", "")
        encoding = headers.get("content-encoding", "")
        signal = path.rstrip("/").rsplit("/", 1)[-1] or "root"
        entry = {
            "path": path,
            "signal": signal,
            "content_type": content_type,
            "content_encoding": encoding,
            "bytes": len(body),
            "auth_headers_present": [h for h in AUTH_HEADERS if h in headers],
            "user_agent": headers.get("user-agent", ""),
        }
        with self.lock:
            self.count += 1
            n = self.count
            with self.log.open("a") as fh:
                fh.write(json.dumps(entry) + "\n")
            if signal == "traces" and not encoding:
                try:
                    decoded = decode_traces(body, content_type)
                except Exception as exc:  # keep recording even when decoding fails
                    decoded = {"decode_error": str(exc)}
                (self.out / f"{n:03d}-traces.json").write_text(json.dumps(decoded, indent=2, sort_keys=True))
            else:
                (self.out / f"{n:03d}-{signal}.bin").write_bytes(body)


def make_handler(sink: Sink):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):  # noqa: N802
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size)
            headers = {k.lower(): v for k, v in self.headers.items()}
            sink.record(self.path, headers, body)
            self.send_response(200)
            self.send_header("Content-Type", headers.get("content-type", "application/json"))
            payload = b"{}" if "json" in headers.get("content-type", "json") else b""
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=14390)
    parser.add_argument("--out", default="./captures")
    args = parser.parse_args()
    sink = Sink(Path(args.out))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(sink))
    print(f"OTLP sink on http://{args.host}:{args.port}/v1/traces -> {args.out}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
