#!/usr/bin/env python3
"""Replay the recorded Koog trace (OTLP/JSON) into a Future AGI project. Standard library only.

This is the no-Kotlin check: it sends the exact payload the recipe produced in a real Koog 1.3.0 run,
with fresh trace/span ids and current timestamps, so ingestion and display can be re-checked without
a JDK. It stands in for the shared round-trip harness until that exists.

usage: replay_fixture.py FIXTURE --project NAME [--base-url URL]   (keys from FI_API_KEY / FI_SECRET_KEY)
       replay_fixture.py FIXTURE --project NAME --dry-run           (print the payload, send nothing)
"""
import argparse
import json
import os
import secrets
import sys
import time
import urllib.request


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def spans_of(requests):
    for req in requests:
        for rs in req.get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                yield from ss.get("spans", [])


def restamp(requests, project, now_ns=None):
    """New ids (parent links kept), times shifted so the run ends now, project_name replaced."""
    now_ns = now_ns or time.time_ns()
    spans = list(spans_of(requests))
    latest_end = max(int(s["endTimeUnixNano"]) for s in spans)
    shift = now_ns - latest_end
    trace_ids, span_ids = {}, {}

    def new_trace(old):
        return trace_ids.setdefault(old, secrets.token_hex(16))

    def new_span(old):
        return span_ids.setdefault(old, secrets.token_hex(8))

    out = json.loads(json.dumps(requests))
    for req in out:
        for rs in req.get("resourceSpans", []):
            attrs = [a for a in rs.get("resource", {}).get("attributes", []) if a["key"] != "project_name"]
            attrs.insert(0, {"key": "project_name", "value": {"stringValue": project}})
            rs.setdefault("resource", {})["attributes"] = attrs
            for ss in rs.get("scopeSpans", []):
                for s in ss.get("spans", []):
                    s["traceId"] = new_trace(s["traceId"])
                    s["spanId"] = new_span(s["spanId"])
                    if s.get("parentSpanId"):
                        s["parentSpanId"] = new_span(s["parentSpanId"])
                    for key in ("startTimeUnixNano", "endTimeUnixNano"):
                        s[key] = str(int(s[key]) + shift)
                    for ev in s.get("events", []):
                        ev["timeUnixNano"] = str(int(ev["timeUnixNano"]) + shift)
    return out, sorted(set(trace_ids.values()))


def post(base_url, body, api_key, secret_key):
    req = urllib.request.Request(
        base_url.rstrip("/") + "/tracer/v1/traces",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key, "X-Secret-Key": secret_key},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture")
    ap.add_argument("--project", required=True)
    ap.add_argument("--base-url", default=os.environ.get("FI_BASE_URL", "https://api.futureagi.com"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    body, traces = restamp(load(a.fixture), a.project)
    if a.dry_run:
        print(json.dumps(body, indent=1))
        return 0
    api_key, secret_key = os.environ.get("FI_API_KEY"), os.environ.get("FI_SECRET_KEY")
    if not api_key or not secret_key:
        print("FI_API_KEY and FI_SECRET_KEY are required", file=sys.stderr)
        return 2
    for req in body:
        post(a.base_url, req, api_key, secret_key)
    print("replayed %d request(s), trace id(s): %s" % (len(body), ", ".join(traces)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
