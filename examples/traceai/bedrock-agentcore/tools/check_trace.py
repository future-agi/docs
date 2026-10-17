#!/usr/bin/env python3
"""Check the stored spans of one scenario (the span list `fi_verify.py --json` writes).

    check_trace.py spans.json happy|failure

happy:   3 invocations of one AgentCore session. Each is its own trace with an
         `agentcore.invocation` root (stored as chain) and at least one tool span and one
         LLM span with model and token counts under it. All spans share one session. The
         first trace is the caller's trace (W3C traceparent sent with the first call).
failure: the root is ERROR with only the exception type name as its status message, and at
         least one span under it is ERROR too (the spans were flushed on the error path). The
         request carried a traceparent without JOIN_CALLER_TRACE: the root has no parent and
         its own trace id.
"""
import json
import sys

PARENT_TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN = "00f067aa0ba902b7"
ROOT = "agentcore.invocation"


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


def main():
    spans = json.load(open(sys.argv[1]))
    mode = sys.argv[2]
    by_trace = {}
    for s in spans:
        by_trace.setdefault(s["trace_id"].replace("-", ""), []).append(s)
    roots = [s for s in spans if s["name"] == ROOT]
    for r in roots:
        if r["observation_type"] != "chain":
            fail(f"root stored as {r['observation_type']}")
    if mode == "happy":
        if len(roots) != 3 or len(by_trace) != 3:
            fail(f"want 3 traces with one {ROOT} root each, got {len(by_trace)} traces / {len(roots)} roots")
        for tid, trace_spans in by_trace.items():
            types = {s["observation_type"] for s in trace_spans}
            if "tool" not in types or "llm" not in types:
                fail(f"trace {tid}: want tool and llm spans, got {sorted(types)}")
            llms = [s for s in trace_spans if s["observation_type"] == "llm"]
            if not all(s["model"] and s["total_tokens"] > 0 for s in llms):
                fail(f"trace {tid}: an llm span has no model or no token counts")
        sessions = {s["session"] for s in spans}
        if len(sessions) != 1 or None in sessions or "" in sessions:
            fail(f"want one session on every span, got {sessions}")
        if PARENT_TRACE not in by_trace:
            fail("the caller's traceparent trace id was not adopted")
        root = next(r for r in roots if r["trace_id"].replace("-", "") == PARENT_TRACE)
        if root["parent_span_id"].replace("-", "")[-16:] != PARENT_SPAN:
            fail(f"root of the caller's trace has parent {root['parent_span_id']}, want {PARENT_SPAN}")
        print(f"ok    happy: 3 traces, {len(spans)} spans, one session, caller trace adopted, tool + llm with model and tokens")
    elif mode == "failure":
        if not roots:
            fail("no root span stored on the error path (not flushed?)")
        for r in roots:
            if r["status"] != "ERROR":
                fail(f"root status {r['status']}")
            if " " in r["status_message"].strip() or not r["status_message"].strip():
                fail("root status message is not a bare exception type name")
        for r in roots:
            if r["parent_span_id"] or r["trace_id"].replace("-", "") == PARENT_TRACE:
                fail("root joined the caller's trace although JOIN_CALLER_TRACE was not set")
        errors = [s for s in spans if s["status"] == "ERROR" and s["name"] != ROOT]
        if not errors:
            fail("no span under the root is ERROR")
        print(f"ok    failure: {len(roots)} ERROR root(s) '{roots[0]['status_message']}', {len(errors)} ERROR child span(s)")
    else:
        fail(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
