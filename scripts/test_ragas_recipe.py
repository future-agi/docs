"""Execute the Ragas recipe with real published packages and a loopback Scores API.

Run in an environment containing the page's pinned requirements:
    python -m unittest discover -s scripts -p test_ragas_recipe.py -v
No Future AGI or model-provider credentials are needed.
"""

import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import re
import threading
import sys
from types import SimpleNamespace
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, patch


def deny_external_network(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
    elif event in ("socket.connect", "socket.sendto"):
        address = args[-1]
        host = address[0] if isinstance(address, tuple) else address
    else:
        return
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Only loopback network access is allowed in this test")


sys.addaudithook(deny_external_network)
os.environ["RAGAS_DO_NOT_TRACK"] = "true"
os.environ["HF_HUB_OFFLINE"] = "1"

PAGE = Path(__file__).resolve().parents[1] / "src/pages/docs/integrations/frameworks/ragas.mdx"
LABEL_ID = "550e8400-e29b-41d4-a716-446655440002"
SPAN_ID = "1234567890abcdef"


class RagasRecipeTests(unittest.TestCase):
    def test_modern_metric_runs_without_a_model(self):
        from ragas.metrics.collections import ExactMatch

        metric = ExactMatch()
        for response, expected in [("30 days", 1.0), ("60 days", 0.0)]:
            result = asyncio.run(metric.ascore(response=response, reference="30 days"))
            self.assertEqual(result.value, expected)

    def test_documented_recipe_posts_scores_to_the_original_span(self):
        # A missing page is the audited regression, not a missing instrumentor.
        self.assertTrue(PAGE.is_file(), "Ragas evaluation recipe is missing")
        code_blocks = re.findall(r"```python\n(.*?)\n```", PAGE.read_text(), re.S)
        self.assertEqual(len(code_blocks), 1)
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, dict(self.headers), body))
                payload = json.dumps({"status": True, "result": {"id": "score-id", **body}}).encode()
                self.send_response(server.response_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.response_status = 200
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        env = {
            "FI_API_KEY": "synthetic-api-key",
            "FI_SECRET_KEY": "synthetic-secret-key",
            "FI_BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "FI_RAGAS_SPAN_ID": SPAN_ID,
            "FI_RAGAS_LABEL_ID": LABEL_ID,
            "RAGAS_DO_NOT_TRACK": "true",
        }
        try:
            with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
                namespace = {"__name__": "__main__"}
                exec(compile(code_blocks[0], str(PAGE), "exec"), namespace)
                self.assertEqual(len(requests), 1)
                score = asyncio.run(namespace["score_span"](
                    span_id=SPAN_ID, response="60 days", reference="30 days", label_id=LABEL_ID,
                ))
                self.assertEqual(score.value, {"value": 0.0})
                for invalid_score in (float("nan"), float("inf"), float("-inf")):
                    with patch.object(namespace["ExactMatch"], "ascore", new=AsyncMock(
                        return_value=SimpleNamespace(value=invalid_score)
                    )), self.assertRaises(ValueError):
                        asyncio.run(namespace["score_span"](
                            span_id=SPAN_ID, response="30 days", reference="30 days", label_id=LABEL_ID,
                        ))
                # Empty or malformed target IDs must not send a score.
                for invalid_id in ("", "not-a-span", "0" * 16):
                    with self.assertRaises(ValueError):
                        asyncio.run(namespace["score_span"](
                            span_id=invalid_id, response="30 days", reference="30 days", label_id=LABEL_ID,
                        ))
                self.assertEqual(len(requests), 2)
                from fi.utils.errors import InvalidAuthError

                server.response_status = 403
                with self.assertRaises(InvalidAuthError):
                    asyncio.run(namespace["score_span"](
                        span_id=SPAN_ID, response="30 days", reference="30 days", label_id=LABEL_ID,
                    ))
            # The SDK can retry a rejected request, but must propagate the error.
            self.assertGreaterEqual(len(requests), 3)
            for request in requests[2:]:
                self.assertEqual(request[2], requests[0][2])
            for (path, headers, body), value in zip(requests[:2], (1.0, 0.0)):
                self.assertEqual(path, "/model-hub/scores/")
                normalized_headers = {key.lower(): val for key, val in headers.items()}
                self.assertEqual(normalized_headers["x-api-key"], "synthetic-api-key")
                self.assertEqual(normalized_headers["x-secret-key"], "synthetic-secret-key")
                self.assertEqual(body["source_type"], "observation_span")
                self.assertEqual(body["source_id"], SPAN_ID)
                self.assertEqual(body["label_id"], LABEL_ID)
                self.assertEqual(body["score_source"], "auto")
                # Numeric annotation values use an object, as consumed by the UI.
                self.assertEqual(body["value"], {"value": value})
                self.assertIn("ragas", body["notes"])
                self.assertNotIn("30 days", json.dumps(body))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
