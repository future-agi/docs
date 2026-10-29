#!/usr/bin/env python3
"""Check the Swiftide span tree that Future AGI stored (PRD AC-01/AC-04/J3, DoD hierarchy).

Reads the span list written by fi_verify.py --json (or any JSON list of span rows with
trace_id, id, parent_span_id, name, status) and checks:

  one-root        every trace has exactly one root span, named agent.query, and no orphans
  steps           every `step` span is a child of agent.query
  children        every `complete`, `tool.*` and `add_message` span is a child of a `step`
  answered        --ok N traces finished without error, each with >= 2 `complete` spans and a
                  successful `tool.get_weather`
  model-error     --model-errors N traces whose agent.query, step and complete are ERROR
  tool-error      --tool-errors N traces with a `tool.get_weather` span in ERROR
  traces          --traces N traces in total

  check_trace.py spans.json --traces 3 --ok 1 --model-errors 1 --tool-errors 1
"""
import argparse
import json
import sys
from collections import defaultdict


def is_error(span: dict) -> bool:
    return str(span.get("status", "")).upper() == "ERROR"


def check(spans: list[dict], a: argparse.Namespace) -> list[tuple[str, bool, str]]:
    traces = defaultdict(list)
    for s in spans:
        traces[s["trace_id"]].append(s)
    rules = []
    roots_ok, orphans, steps_ok, children_ok = True, 0, True, True
    ok = model_err = tool_err = 0
    for spans_in in traces.values():
        by_id = {s["id"]: s for s in spans_in}
        roots = [s for s in spans_in if not s.get("parent_span_id")]
        orphans += sum(1 for s in spans_in if s.get("parent_span_id") and s["parent_span_id"] not in by_id)
        if len(roots) != 1 or roots[0]["name"] != "agent.query":
            roots_ok = False
            continue
        root = roots[0]
        parent_name = {s["id"]: by_id.get(s.get("parent_span_id"), {}).get("name") for s in spans_in}
        for s in spans_in:
            if s["name"] == "step" and parent_name[s["id"]] != "agent.query":
                steps_ok = False
            if (s["name"] in ("complete", "add_message") or s["name"].startswith("tool.")) and parent_name[s["id"]] != "step":
                children_ok = False
        completes = [s for s in spans_in if s["name"] == "complete"]
        weather = [s for s in spans_in if s["name"] == "tool.get_weather"]
        if not is_error(root) and len(completes) >= 2 and any(not is_error(w) for w in weather):
            ok += 1
        if is_error(root) and any(is_error(c) for c in completes) and any(s["name"] == "step" and is_error(s) for s in spans_in):
            model_err += 1
        if any(is_error(w) for w in weather):
            tool_err += 1
    rules.append(("one-root", roots_ok and orphans == 0, f"{len(traces)} trace(s), orphans={orphans}"))
    rules.append(("steps", steps_ok, "step spans under agent.query"))
    rules.append(("children", children_ok, "complete / tool.* / add_message under a step"))
    if a.traces is not None:
        rules.append(("traces", len(traces) == a.traces, f"{len(traces)} == {a.traces}"))
    if a.ok is not None:
        rules.append(("answered", ok == a.ok, f"{ok} == {a.ok}"))
    if a.model_errors is not None:
        rules.append(("model-error", model_err == a.model_errors, f"{model_err} == {a.model_errors}"))
    if a.tool_errors is not None:
        rules.append(("tool-error", tool_err == a.tool_errors, f"{tool_err} == {a.tool_errors}"))
    return rules


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spans")
    ap.add_argument("--traces", type=int)
    ap.add_argument("--ok", type=int)
    ap.add_argument("--model-errors", type=int)
    ap.add_argument("--tool-errors", type=int)
    a = ap.parse_args()
    with open(a.spans) as f:
        spans = json.load(f)
    if isinstance(spans, dict):
        spans = spans.get("spans", [])
    rules = check(spans, a)
    for name, passed, detail in rules:
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")
    passed = bool(spans) and all(p for _, p, _ in rules)
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
