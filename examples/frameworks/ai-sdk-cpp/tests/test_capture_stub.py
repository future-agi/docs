"""The loopback capture stub records requests, redacts Authorization, and binds to loopback only."""
import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "wire_probe"))
import capture_stub  # noqa: E402


class CaptureStubTest(unittest.TestCase):
    def test_records_post_and_redacts_authorization(self):
        out = os.path.join(tempfile.mkdtemp(), "cap.jsonl")
        server = capture_stub.make_server(out, 0)
        self.assertEqual(server.server_address[0], "127.0.0.1")
        t = threading.Thread(target=server.handle_request)
        t.start()
        auth = base64.b64encode(b"pk-lf-fake:sk-lf-fake").decode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/public/ingestion",
            data=json.dumps({"batch": [{"type": "trace-create"}]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Basic " + auth},
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 207)
        t.join()
        server.server_close()
        with open(out) as f:
            rec = json.loads(f.readline())
        self.assertEqual(rec["path"], "/api/public/ingestion")
        self.assertEqual(rec["basic_auth_user"], "pk-lf-fake")
        self.assertEqual(rec["headers"]["Authorization"], "<redacted>")
        self.assertNotIn("sk-lf-fake", json.dumps(rec))
        self.assertEqual(rec["body"]["batch"][0]["type"], "trace-create")


if __name__ == "__main__":
    unittest.main()
