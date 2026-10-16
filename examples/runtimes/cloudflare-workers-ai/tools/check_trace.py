#!/usr/bin/env python3
"""Check stored spans (the list fi_verify.py --json writes).   check_trace.py spans.json happy|failure"""
import json
import sys


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


def main():
    spans = json.load(open(sys.argv[1]))
    mode = sys.argv[2]
    roots = [s for s in spans if s["name"] == "worker.fetch"]
    ais = [s for s in spans if s["name"] == "workers_ai.run"]
    traces = {s["trace_id"] for s in spans}
    for a in ais:
        if not any(r["id"] == a["parent_span_id"] and r["trace_id"] == a["trace_id"] for r in roots):
            fail("workers_ai.run is not a child of worker.fetch in the same trace")
        if a["observation_type"] != "llm":
            fail(f"workers_ai.run stored as {a['observation_type']}")
    for r in roots:
        if r["observation_type"] != "chain":
            fail(f"root stored as {r['observation_type']}")
    if len(roots) != len(ais) or len(roots) != len(traces) or not roots:
        fail(f"want N roots / N AI children / N traces, got {len(roots)}/{len(ais)}/{len(traces)}")
    if mode == "happy":
        if any(s["status"] == "ERROR" for s in spans):
            fail("unexpected ERROR span")
        for a in ais:
            if a["model"] != "@cf/meta/llama-3.1-8b-instruct":
                fail(f"model stored as {a['model']!r}")
            if not (a["prompt_tokens"] and a["completion_tokens"]):
                fail("token counts missing on the AI span")
    else:
        # the failure scenario sends one failing request and one good request
        if len(roots) != 2:
            fail(f"want 2 traces (one failed, one ok), got {len(roots)}")
        if sorted(s["name"] for s in spans if s["status"] == "ERROR") != ["worker.fetch", "workers_ai.run"]:
            fail(f"ERROR spans: {[s['name'] for s in spans if s['status'] == 'ERROR']}")
        if any(len(s["status_message"]) > 40 for s in spans if s["status"] == "ERROR"):
            fail("error status message is not just the error type")
    print(f"OK {mode}: {len(traces)} traces, {len(spans)} spans")
    print("trace_ids", ",".join(sorted(traces)))


if __name__ == "__main__":
    main()
