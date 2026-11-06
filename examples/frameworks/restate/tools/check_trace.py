#!/usr/bin/env python3
"""Check stored Restate traces against the durable-execution rules.

Input is the span list that fi_verify.py --json writes (one dict per stored span with
trace_id, id, parent_span_id, name, observation_type, status, attrs_string).

  check_trace.py spans.json [--invocations 3] [--model-steps 2]

Rules, each one printed as PASS/FAIL:
  one-trace-per-invocation  every restate.invocation.id is in exactly one trace
  trace-per-invocation      different invocations never share a trace
  parent-is-attempt         every llm/tool span's parent is an invocation-attempt span of its trace
  no-replay-duplicates      a successful invocation has exactly --model-steps OK llm spans,
                            however many attempts it took (journaled steps are not re-emitted)
  invocations               with --invocations N: exactly N invocations were stored

Exit 0 when every rule passes, 1 otherwise. Prints span names and counts, never content.
"""
import argparse
import json
import sys
from collections import defaultdict

RESTATE_PREFIXES = ("ingress ", "invocation-start ", "invocation-attempt ", "invocation-end ")


def attrs(span: dict) -> dict:
    a = span.get("attrs_string") or {}
    return a if isinstance(a, dict) else {}


def summarize(spans: list[dict]) -> dict:
    by_trace = defaultdict(list)
    for s in spans:
        by_trace[s["trace_id"]].append(s)
    invocations = defaultdict(set)  # invocation id -> trace ids
    per_trace = {}
    for tid, ss in by_trace.items():
        attempt_ids = {s["id"] for s in ss if s["name"].startswith("invocation-attempt ")}
        inv_ids = {attrs(s).get("restate.invocation.id") for s in ss if s["name"].startswith(RESTATE_PREFIXES)}
        inv_ids.discard(None)
        for inv in inv_ids:
            invocations[inv].add(tid)
        app = [s for s in ss if (s.get("observation_type") or "").lower() in ("llm", "tool")]
        end = [s for s in ss if s["name"].startswith("invocation-end ")]
        per_trace[tid] = {
            "invocation_ids": sorted(inv_ids),
            "attempts": len(attempt_ids),
            "attempts_error": sum(1 for s in ss if s["id"] in attempt_ids and s["status"] == "ERROR"),
            "llm_ok": sum(1 for s in app if s["observation_type"].lower() == "llm" and s["status"] != "ERROR"),
            "llm_error": sum(1 for s in app if s["observation_type"].lower() == "llm" and s["status"] == "ERROR"),
            "tool_ok": sum(1 for s in app if s["observation_type"].lower() == "tool" and s["status"] != "ERROR"),
            "tool_error": sum(1 for s in app if s["observation_type"].lower() == "tool" and s["status"] == "ERROR"),
            "orphans": sorted(s["name"] for s in app if s.get("parent_span_id") not in attempt_ids),
            "result": attrs(end[0]).get("restate.invocation.result") if end else None,
            "end_status": end[0]["status"] if end else None,
        }
    return {"traces": per_trace, "invocations": {k: sorted(v) for k, v in invocations.items()}}


def check(summary: dict, invocations: int | None, model_steps: int | None) -> list[tuple[str, bool, str]]:
    traces, invs = summary["traces"], summary["invocations"]
    results = []
    multi = {k: v for k, v in invs.items() if len(v) != 1}
    results.append(("one-trace-per-invocation", not multi and bool(invs), f"{len(invs)} invocation(s), split: {len(multi)}"))
    shared = {t: v["invocation_ids"] for t, v in traces.items() if len(v["invocation_ids"]) > 1}
    results.append(("trace-per-invocation", not shared, f"{len(traces)} trace(s), shared: {len(shared)}"))
    orphans = {t: v["orphans"] for t, v in traces.items() if v["orphans"]}
    results.append(("parent-is-attempt", not orphans, f"orphan llm/tool spans: {sum(len(o) for o in orphans.values())}"))
    if model_steps is not None:
        bad = {t: v["llm_ok"] for t, v in traces.items() if v["result"] == "success" and v["llm_ok"] != model_steps}
        ok = [t for t, v in traces.items() if v["result"] == "success"]
        results.append(("no-replay-duplicates", not bad and bool(ok), f"{len(ok)} successful invocation(s), wrong llm count: {bad}"))
    if invocations is not None:
        results.append(("invocations", len(invs) == invocations, f"expected {invocations}, stored {len(invs)}"))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spans")
    ap.add_argument("--invocations", type=int)
    ap.add_argument("--model-steps", type=int)
    ap.add_argument("--json", help="write the summary here")
    a = ap.parse_args()
    with open(a.spans) as f:
        spans = json.load(f)
    summary = summarize(spans)
    for tid, v in summary["traces"].items():
        print(
            f"trace {tid}: attempts={v['attempts']} (error {v['attempts_error']}) llm ok/error={v['llm_ok']}/{v['llm_error']} "
            f"tool ok/error={v['tool_ok']}/{v['tool_error']} result={v['result']} end_status={v['end_status']}"
        )
    results = check(summary, a.invocations, a.model_steps)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"summary": summary, "rules": results}, f, indent=1)
    passed = all(ok for _, ok, _ in results)
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
