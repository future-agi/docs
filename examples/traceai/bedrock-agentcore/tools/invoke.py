#!/usr/bin/env python3
"""Call a running AgentCore app the way InvokeAgentRuntime does: POST /invocations with the session header.

    invoke.py URL SESSION_ID PROMPT [PROMPT ...] [--traceparent TP]

The traceparent, when given, is sent with the first invocation only. Prints one line per call:
`status=<http status> seconds=<s>` and, for a 200, the agent's answer length (not the answer).
Exit 0 always; the caller checks the lines.
"""
import argparse
import json
import time
import urllib.error
import urllib.request

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("session_id")
    ap.add_argument("prompts", nargs="+")
    ap.add_argument("--traceparent")
    a = ap.parse_args()
    for i, prompt in enumerate(a.prompts):
        headers = {"Content-Type": "application/json", SESSION_HEADER: a.session_id}
        if a.traceparent and i == 0:
            headers["traceparent"] = a.traceparent
        req = urllib.request.Request(a.url.rstrip("/") + "/invocations", method="POST", headers=headers,
                                     data=json.dumps({"prompt": prompt}).encode())
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read() or b"{}")
                print(f"status={resp.status} seconds={time.time() - t0:.1f} answer_chars={len(str(body.get('result', '')))}")
        except urllib.error.HTTPError as err:
            print(f"status={err.code} seconds={time.time() - t0:.1f}")
        except Exception as err:  # connection refused, timeout
            print(f"status=error:{type(err).__name__} seconds={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
