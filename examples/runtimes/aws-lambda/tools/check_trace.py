#!/usr/bin/env python3
"""Check the stored spans of a happy / failure run (the span list fi_verify.py --json writes).

    check_trace.py spans.json happy|failure
"""
import json
import sys

PARENT_TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN = "00f067aa0ba902b7"


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


def main():
    spans = json.load(open(sys.argv[1]))
    mode = sys.argv[2]
    by_trace = {}
    for s in spans:
        by_trace.setdefault(s["trace_id"], []).append(s)
    roots = [s for s in spans if s["name"] == "lambda.handler"]
    tools = [s for s in spans if s["name"] == "lookup_order"]
    for t in tools:
        parent = next((r for r in roots if r["id"] == t["parent_span_id"] and r["trace_id"] == t["trace_id"]), None)
        if not parent:
            fail("tool span is not a child of a lambda.handler span in the same trace")
        if t["observation_type"] != "tool":
            fail(f"tool span stored as {t['observation_type']}")
    for r in roots:
        if r["observation_type"] != "chain":
            fail(f"root stored as {r['observation_type']}")
    if mode == "happy":
        if len(roots) != 3 or len(tools) != 3 or len(by_trace) != 3:
            fail(f"want 3 roots/3 tools/3 traces, got {len(roots)}/{len(tools)}/{len(by_trace)}")
        by_tid = {r["trace_id"].replace("-", ""): r for r in roots}
        if PARENT_TRACE not in by_tid:
            fail("the API Gateway traceparent trace id was not adopted")
        gw = by_tid[PARENT_TRACE]
        if gw["parent_span_id"] != PARENT_SPAN:
            fail(f"API Gateway root parent is {gw['parent_span_id']}")
        others = [r for r in roots if r is not gw]
        if any(r["parent_span_id"] for r in others):
            fail("a direct/SQS invocation got a parent")
        if any(s["status"] == "ERROR" for s in spans):
            fail("unexpected ERROR span")
    else:
        errs = [s for s in spans if s["status"] == "ERROR"]
        if sorted(s["name"] for s in errs) != ["lambda.handler", "lookup_order"]:
            fail(f"ERROR spans: {[s['name'] for s in errs]}")
        if len(roots) != 2 or len(by_trace) != 2:
            fail(f"want 2 traces (the failed and the following warm invocation), got {len(by_trace)}")
        if any(len(e["status_message"]) > 40 for e in errs):
            fail("error status message is not just the error type")
    print(f"OK {mode}: {len(by_trace)} traces, {len(spans)} spans")
    print("trace_ids", ",".join(sorted(by_trace)))


if __name__ == "__main__":
    main()
