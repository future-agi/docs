"""Emulates how the Claude API delivers spans to a telemetry destination, per
https://platform.claude.com/docs/en/manage-claude/opentelemetry/api
("Delivery and health", read 2026-10-16):

  * OTLP/HTTP protobuf, POST <endpoint>/v1/traces
  * the destination's own request headers, nothing else added
  * User-Agent: Claude-Platform
  * first request gzip-compressed with Content-Encoding: gzip;
    on a 400 or 415 answer, the same spans are sent again right away uncompressed

STANDIN: this is our script, not Anthropic's delivery service.
Header values are read from the environment and never printed.
"""
from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request


def _post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "replace")
    except Exception as e:  # connection refused etc.
        return -1, type(e).__name__


def deliver_like_claude_platform(url: str, payload: bytes, destination_headers: dict[str, str]) -> dict:
    base = {"Content-Type": "application/x-protobuf", "User-Agent": "Claude-Platform", **destination_headers}
    first_status, first_body = _post(url, gzip.compress(payload), {**base, "Content-Encoding": "gzip"})
    attempts = [{"compression": "gzip", "status": first_status, "body": first_body}]
    if first_status in (400, 415):
        st, bd = _post(url, payload, base)
        attempts.append({"compression": "none", "status": st, "body": bd})
    final = attempts[-1]["status"]
    return {"attempts": attempts, "delivered": 200 <= final < 300}


if __name__ == "__main__":
    import sys
    print(json.dumps(deliver_like_claude_platform(sys.argv[1], b"", {}), indent=1))
