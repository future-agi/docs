"""The wire tap records decoded OTLP, redacts credentials, and forwards the request unchanged."""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import wire_tap
from post_batch import post_http
from tfy_batch import build_batch


class Sink(BaseHTTPRequestHandler):
    got = []

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        Sink.got.append((self.path, dict(self.headers), self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def test_tap_records_redacts_and_forwards(tmp_path):
    sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    out = tmp_path / "wire.jsonl"
    wire_tap.args = type("A", (), {"forward": f"http://127.0.0.1:{sink.server_port}", "out": str(out)})()
    tap = ThreadingHTTPServer(("127.0.0.1", 0), wire_tap.Tap)
    threading.Thread(target=tap.serve_forever, daemon=True).start()
    try:
        req = build_batch("TAPMARK")
        status, _ = post_http(
            f"http://127.0.0.1:{tap.server_port}/v1/traces", req,
            encoding="proto", headers={"X-Api-Key": "very-secret", "X-Secret-Key": "also-secret"}, gzip_body=False,
        )
    finally:
        tap.shutdown()
        sink.shutdown()
    assert status == 200
    record = json.loads(out.read_text().splitlines()[0])
    assert record["path"] == "/v1/traces"
    assert record["headers"]["x-api-key"] == "<redacted>" and "very-secret" not in out.read_text()
    assert "TAPMARK" in json.dumps(record["body"])
    (path, headers, body), = Sink.got
    assert path == "/v1/traces" and headers["X-Api-Key"] == "very-secret"
    assert body == req.SerializeToString()
