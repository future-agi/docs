#!/usr/bin/env python3
"""Check stored weather-agent traces: one trace per run, the right span kinds under the right parents.

Input is the span list that fi_verify.py --json writes (one dict per stored span with trace_id, id,
parent_span_id, name, observation_type, status, status_message, model, provider, prompt_tokens,
completion_tokens, session, attrs_string).

  check_trace.py spans.json [--traces 3] [--tool-error] [--failed-run] [--content-off]

Rules, each printed as PASS/FAIL:
  one-root            every trace has exactly one root span, the "weather-agent" chain span
  hierarchy           agent and tool spans sit under the root; llm spans sit under an agent span
  llm-details         every OK llm span has a model, provider "openai" and prompt/completion tokens
  session             every root span has an Observe session (from conversation.id)
  traces              with --traces N: exactly N traces were stored
  tool-error          with --tool-error: a tool span is ERROR inside a trace whose root is OK
  failed-run          with --failed-run: a trace whose root, agent and llm spans are ERROR
  content-off         with --content-off: no input/output stored, error text is "error", no user.id
Exit 0 when every rule passes, 1 otherwise. Prints span names, kinds and counts, never content.
"""
import argparse
import json
import sys
from collections import defaultdict


def kind(span: dict) -> str:
    return (span.get("observation_type") or "").lower()


def attrs(span: dict) -> dict:
    a = span.get("attrs_string") or {}
    return a if isinstance(a, dict) else {}


def rules(spans: list[dict], a: argparse.Namespace) -> list[tuple[str, bool, str]]:
    traces = defaultdict(list)
    for s in spans:
        traces[s["trace_id"]].append(s)
    roots, bad_tree, bad_llm, no_session = {}, [], [], []
    for tid, ss in traces.items():
        ids = {s["id"]: s for s in ss}
        top = [s for s in ss if not s.get("parent_span_id") or s["parent_span_id"] not in ids]
        if len(top) == 1 and top[0]["name"] == "weather-agent" and kind(top[0]) == "chain":
            roots[tid] = top[0]
            if not top[0].get("session"):
                no_session.append(tid[:8])
        for s in ss:
            parent = ids.get(s.get("parent_span_id"))
            if kind(s) in ("agent", "tool") and (parent is None or parent["name"] != "weather-agent"):
                bad_tree.append(f"{s['name']}({kind(s)})")
            if kind(s) == "llm" and (parent is None or kind(parent) != "agent"):
                bad_tree.append(f"{s['name']}(llm)")
            if kind(s) == "llm" and s["status"] != "ERROR":
                if not (s.get("model") and s.get("provider") == "openai" and s.get("prompt_tokens") and s.get("completion_tokens")):
                    bad_llm.append(s["name"])
    out = [
        ("one-root", len(roots) == len(traces) and bool(traces), f"{len(roots)}/{len(traces)} traces have one weather-agent chain root"),
        ("hierarchy", not bad_tree, f"misplaced: {bad_tree}"),
        ("llm-details", not bad_llm and any(kind(s) == "llm" for s in spans), f"llm spans missing model/provider/tokens: {bad_llm}"),
        ("session", not no_session, f"roots without a session: {no_session}"),
    ]
    if a.traces is not None:
        out.append(("traces", len(traces) == a.traces, f"{len(traces)} stored, expected {a.traces}"))
    if a.tool_error:
        hit = [tid for tid, ss in traces.items() if tid in roots and roots[tid]["status"] != "ERROR"
               and any(kind(s) == "tool" and s["status"] == "ERROR" for s in ss)]
        out.append(("tool-error", bool(hit), f"traces with a failed tool call that still answered: {len(hit)}"))
    if a.failed_run:
        hit = [tid for tid, ss in traces.items() if tid in roots and roots[tid]["status"] == "ERROR"
               and any(kind(s) == "agent" and s["status"] == "ERROR" for s in ss)
               and any(kind(s) == "llm" and s["status"] == "ERROR" for s in ss)]
        out.append(("failed-run", bool(hit), f"traces where the model call failed the run: {len(hit)}"))
    if a.content_off:
        leaks = [s["name"] for s in spans if s.get("input_length") or s.get("output_length")
                 or (s["status"] == "ERROR" and s.get("status_message") not in ("error", "", None))
                 or {"input.value", "output.value", "user.id", "tool.input", "tool.output"} & set(attrs(s))]
        out.append(("content-off", not leaks, f"spans with input/output/error text/user.id: {leaks}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spans")
    ap.add_argument("--traces", type=int)
    ap.add_argument("--tool-error", action="store_true")
    ap.add_argument("--failed-run", action="store_true")
    ap.add_argument("--content-off", action="store_true")
    a = ap.parse_args()
    with open(a.spans) as f:
        spans = json.load(f)
    counts = defaultdict(int)
    for s in spans:
        counts[f"{kind(s)}:{s['name']}:{s['status'] or 'UNSET'}"] += 1
    print(json.dumps({"spans": len(spans), "by_kind_name_status": dict(sorted(counts.items()))}))
    result = rules(spans, a)
    for name, ok, detail in result:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    passed = all(ok for _, ok, _ in result)
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
