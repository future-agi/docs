"""Post a recorded OTLP/JSON fixture to Future AGI, with fresh ids and timestamps.

The tree, names, attributes and statuses stay as recorded. The resource ``project_name``
is set to $FI_PROJECT_NAME. No model call is made.

usage: FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=... FI_PROJECT_NAME=... \
       python scripts/replay_fixture.py fixtures/<file>.otlp.json
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import sys
import time
import urllib.request


def refresh(payload: dict, project_name: str) -> dict:
    payload = copy.deepcopy(payload)
    spans = [s for rs in payload["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]
    trace_ids = {s["traceId"]: secrets.token_hex(16) for s in spans}
    span_ids = {s["spanId"]: secrets.token_hex(8) for s in spans}
    shift = time.time_ns() - max(int(s["endTimeUnixNano"]) for s in spans)
    for span in spans:
        span["traceId"] = trace_ids[span["traceId"]]
        span["spanId"] = span_ids[span["spanId"]]
        if span.get("parentSpanId"):
            span["parentSpanId"] = span_ids.get(span["parentSpanId"], span["parentSpanId"])
        for key in ("startTimeUnixNano", "endTimeUnixNano"):
            span[key] = str(int(span[key]) + shift)
        for event in span.get("events", []):
            event["timeUnixNano"] = str(int(event["timeUnixNano"]) + shift)
    for rs in payload["resourceSpans"]:
        for attribute in rs["resource"]["attributes"]:
            if attribute["key"] == "project_name":
                attribute["value"] = {"stringValue": project_name}
    return payload


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = refresh(json.load(handle), os.environ["FI_PROJECT_NAME"])
    base = os.environ.get("FI_BASE_URL", "https://api.futureagi.com").rstrip("/")
    request = urllib.request.Request(
        f"{base}/tracer/v1/traces",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": os.environ["FI_API_KEY"],
            "X-Secret-Key": os.environ["FI_SECRET_KEY"],
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print("status", response.status)
    ids = sorted({s["traceId"] for rs in payload["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]})
    print("trace ids", " ".join(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
