#!/usr/bin/env python3
"""POST recorded Cowork OTLP/JSON log exports to a running bridge, as Cowork would.

    python3 replay.py tests/fixtures/cowork-documented-session.jsonl \
        --url http://127.0.0.1:4320/v1/logs [--token TOKEN] [--sleep 1]

Every run swaps the fixture's session.id and prompt.id values for fresh UUIDs,
so each replay lands as new traces, and prints the new ids.
"""
import argparse
import json
import time
import urllib.request
import uuid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture")
    ap.add_argument("--url", default="http://127.0.0.1:4320/v1/logs")
    ap.add_argument("--token", default="")
    ap.add_argument("--sleep", type=float, default=1.0)
    a = ap.parse_args()
    lines = [line for line in open(a.fixture).read().splitlines() if line.strip()]
    ids = {}
    for line in lines:
        for rl in json.loads(line)["resourceLogs"]:
            for sl in rl["scopeLogs"]:
                for rec in sl["logRecords"]:
                    for attr in rec["attributes"]:
                        if attr["key"] in ("session.id", "prompt.id"):
                            ids.setdefault(attr["value"]["stringValue"], str(uuid.uuid4()))
    for i, line in enumerate(lines):
        for old, new in ids.items():
            line = line.replace(old, new)
        headers = {"Content-Type": "application/json"}
        if a.token:
            headers["Authorization"] = "Bearer " + a.token
        req = urllib.request.Request(a.url, data=line.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"batch {i + 1}/{len(lines)} http={r.status}")
        time.sleep(a.sleep)
    for old, new in ids.items():
        print(f"{old} -> {new}")


if __name__ == "__main__":
    main()
