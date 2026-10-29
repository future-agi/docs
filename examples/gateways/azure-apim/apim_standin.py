#!/usr/bin/env python3
"""STAND-IN for an Azure API Management API that forwards OTLP traces to Future AGI.

THIS IS NOT AZURE. It models, in ~100 lines, what policy/otlp-egress.policy.xml tells APIM to do, so the
real OpenTelemetry client and the real Future AGI collector can be exercised without an Azure subscription.
How APIM itself behaves (header handling, body limits, content-encoding, logging) was NOT verified here.

What it does, mirroring the policy:
  * serves one operation, POST /tracer/v1/traces (API URL suffix `tracer`, operation `/v1/traces`);
    any other path or method answers 404, like APIM's "Resource not found"
  * requires a subscription key in `Ocp-Apim-Subscription-Key` (or `?subscription-key=`) when
    --subscription-key is given; a missing or wrong key answers 401 and nothing is forwarded
  * removes the caller's Ocp-Apim-Subscription-Key and Authorization headers
  * sets X-Api-Key and X-Secret-Key from the environment (APIM named values `fi-api-key`, `fi-secret-key`)
  * forwards the body unchanged to --backend and returns the backend's status and body unchanged

Environment: FI_API_KEY, FI_SECRET_KEY (the gateway's keys; the calling app never sees them).
Usage: apim_standin.py --backend http://localhost:4318/tracer/v1/traces [--port 18298] [--subscription-key K]
"""
import argparse
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

OPERATION = "/tracer/v1/traces"
# Headers a gateway must not blindly copy to the backend.
HOP_BY_HOP = {"host", "connection", "content-length", "transfer-encoding", "keep-alive", "accept-encoding"}
STRIPPED = {"ocp-apim-subscription-key", "authorization", "x-api-key", "x-secret-key"}


def make_handler(backend, subscription_key, api_key, secret_key, log):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _reply(self, status, body, ctype="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _deny(self, status, message):
            self._reply(status, ('{"statusCode": %d, "message": "%s"}' % (status, message)).encode())

        def do_GET(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self._deny(404, "Resource not found")

        do_PUT = do_DELETE = do_PATCH = do_GET

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            url = urlparse(self.path)
            if url.path != OPERATION:
                return self._deny(404, "Resource not found")
            supplied = self.headers.get("Ocp-Apim-Subscription-Key") or (parse_qs(url.query).get("subscription-key") or [None])[0]
            if subscription_key and supplied != subscription_key:
                return self._deny(401, "Access denied due to missing or invalid subscription key.")
            # --- the policy: delete caller credentials, set the two Future AGI headers ---
            fwd = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP | STRIPPED}
            fwd["X-Api-Key"] = api_key
            fwd["X-Secret-Key"] = secret_key
            req = urllib.request.Request(backend, data=body, headers=fwd, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status, out, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "application/x-protobuf")
            except urllib.error.HTTPError as exc:
                status, out, ctype = exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")
            except OSError as exc:
                return self._deny(502, "Backend unreachable: %s" % type(exc).__name__)
            log(f"forwarded {len(body)} bytes -> HTTP {status}")
            self._reply(status, out, ctype)

    return Handler


def serve(backend, port=0, subscription_key=None, api_key="", secret_key="", log=lambda m: None):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(backend, subscription_key, api_key, secret_key, log))
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", required=True, help="Future AGI traces URL, e.g. http://localhost:4318/tracer/v1/traces")
    ap.add_argument("--port", type=int, default=18298)
    ap.add_argument("--subscription-key", default=os.environ.get("APIM_SUBSCRIPTION_KEY"))
    a = ap.parse_args()
    api_key, secret_key = os.environ.get("FI_API_KEY"), os.environ.get("FI_SECRET_KEY")
    if not api_key or not secret_key:
        print("set FI_API_KEY and FI_SECRET_KEY (the stand-in plays the policy that holds them)", file=sys.stderr)
        return 2
    server = serve(a.backend, a.port, a.subscription_key, api_key, secret_key, log=lambda m: print(m, flush=True))
    print(f"STAND-IN (not Azure) on http://127.0.0.1:{server.server_address[1]}{OPERATION} -> {a.backend}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
