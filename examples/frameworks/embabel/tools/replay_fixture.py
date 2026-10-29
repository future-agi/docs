#!/usr/bin/env python3
"""Replay the recorded Embabel 1.5.3 trace (content off) to a Future AGI collector, no JVM or model needed.

The fixture is what the example app really sent (OTLP, captured on the wire, decoded to OTLP/JSON,
project_name replaced). Each replay gets fresh trace and span ids, so it can be sent repeatedly.

  replay_fixture.py --project my-project            # needs FI_API_KEY, FI_SECRET_KEY; FI_BASE_URL optional

Prints the new trace id. Exit 0 when the collector answers 2xx.
"""
import argparse
import copy
import json
import os
import secrets
import sys
import time
import urllib.request
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "embabel_1.5.3_weather_agent_content_off.json"


def fresh_copy(payload: dict, project: str) -> tuple[dict, str]:
    """Same tree with new ids, timestamps moved to now, and the given project_name."""
    out = copy.deepcopy(payload)
    trace_id = secrets.token_hex(16)
    span_ids: dict[str, str] = {}
    spans = [sp for rs in out["resourceSpans"] for ss in rs["scopeSpans"] for sp in ss["spans"]]
    shift = time.time_ns() - max(int(sp["endTimeUnixNano"]) for sp in spans)
    for sp in spans:
        span_ids[sp["spanId"]] = secrets.token_hex(8)
    for rs in out["resourceSpans"]:
        for a in rs["resource"]["attributes"]:
            if a["key"] == "project_name":
                a["value"] = {"stringValue": project}
    for sp in spans:
        sp["traceId"] = trace_id
        sp["spanId"] = span_ids[sp["spanId"]]
        if sp.get("parentSpanId"):
            sp["parentSpanId"] = span_ids.get(sp["parentSpanId"], "")
        for key in ("startTimeUnixNano", "endTimeUnixNano"):
            sp[key] = str(int(sp[key]) + shift)
    return out, trace_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    base = os.environ.get("FI_BASE_URL", "https://api.futureagi.com").rstrip("/")
    body, trace_id = fresh_copy(json.loads(FIXTURE.read_text()), a.project)
    req = urllib.request.Request(f"{base}/tracer/v1/traces", data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json",
        "X-Api-Key": os.environ["FI_API_KEY"],
        "X-Secret-Key": os.environ["FI_SECRET_KEY"],
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"HTTP {resp.status}; trace id {trace_id[:8]}-{trace_id[8:12]}-{trace_id[12:16]}-{trace_id[16:20]}-{trace_id[20:]}")
        return 0 if 200 <= resp.status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
