#!/usr/bin/env python3
"""STAND-IN for the TrueFoundry AI Gateway. For local tests only.

This is NOT TrueFoundry code and does not behave like a TrueFoundry gateway
beyond the surface the TrueFoundry docs describe:

  * POST {base}/chat/completions at the root, no /v1 prefix
    (https://www.truefoundry.com/docs/ai-gateway/making-llm-requests-via-gateway)
  * model id is `provider_account/model_name`, for example `openai-main/gpt-4o-mini`
  * the caller sends a TrueFoundry token as `Authorization: Bearer <token>`
  * a model the caller cannot use, or that does not exist, returns HTTP 403
    (https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes,
    "Authorization vs missing model")

The error body shape is an assumption (an OpenAI-style error envelope). The real
gateway's body is not documented on those pages.

Requests that pass those checks are forwarded to any OpenAI-compatible upstream
(for example a local proxy) with the provider-account prefix removed.

Environment:
  STANDIN_UPSTREAM_BASE_URL   upstream base URL, for example http://127.0.0.1:8317/v1
  STANDIN_UPSTREAM_API_KEY    upstream key (never logged)
  STANDIN_TOKEN               token the client must send (default: tfy-standin-token)
  STANDIN_MODELS              comma list of `account/model` ids that are allowed,
                              default: openai-main/gpt-6-luna
  STANDIN_PORT                listen port (default 18304)
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("STANDIN_TOKEN", "tfy-standin-token")
ALLOWED = [m.strip() for m in os.environ.get("STANDIN_MODELS", "openai-main/gpt-6-luna").split(",") if m.strip()]
UPSTREAM = os.environ.get("STANDIN_UPSTREAM_BASE_URL", "").rstrip("/")
UPSTREAM_KEY = os.environ.get("STANDIN_UPSTREAM_API_KEY", "")


def error_body(status: int, message: str) -> bytes:
    return json.dumps({"error": {"message": message, "type": "standin_error", "code": status}}).encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # request lines only, no headers or bodies
        sys.stderr.write("standin-gateway: %s\n" % (fmt % args))

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        if self.path != "/chat/completions":
            self._send(404, error_body(404, "stand-in only serves POST /chat/completions"))
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        if self.headers.get("Authorization", "") != f"Bearer {TOKEN}":
            self._send(401, error_body(401, "invalid or missing token"))
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, error_body(400, "body is not JSON"))
            return
        model = payload.get("model", "")
        if model not in ALLOWED:
            # Same client message for "forbidden" and "does not exist", as the TrueFoundry docs describe.
            self._send(403, error_body(403, "You are not authorized to use this model or the model does not exist"))
            return
        if not UPSTREAM:
            self._send(502, error_body(502, "STANDIN_UPSTREAM_BASE_URL is not set"))
            return
        payload["model"] = model.split("/", 1)[1]
        req = urllib.request.Request(
            UPSTREAM + "/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {UPSTREAM_KEY}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
                self._send(resp.status, body, resp.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as exc:
            self._send(exc.code, exc.read() or error_body(exc.code, "upstream error"))
        except Exception as exc:  # network failure to the upstream
            self._send(502, error_body(502, f"upstream unreachable: {type(exc).__name__}"))


def main() -> None:
    port = int(os.environ.get("STANDIN_PORT", "18304"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"STAND-IN TrueFoundry gateway on http://127.0.0.1:{port} (not TrueFoundry code)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
