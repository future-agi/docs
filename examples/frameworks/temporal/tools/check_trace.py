#!/usr/bin/env python3
"""Check the stored trace of one Temporal workflow against the tracing rules of the recipe.

Input is the span list that fi_verify.py --json writes (one dict per stored span with trace_id, id,
parent_span_id, name, observation_type, status, attrs_string).

  check_trace.py spans.json [--workflow WORKFLOW_ID] [--expect NAME=COUNT ...] [--errors NAME=COUNT ...]
                 [--no-start-workflow] [--llm-spans N] [--ignore NAME_PREFIX ...]

The spans of a workflow are the stored spans whose session.id (set by tracing.py) or
temporalWorkflowID attribute is WORKFLOW_ID (without --workflow: every stored span). Spans whose name
starts with an --ignore prefix are left out (a signal sent from outside the trace starts its own
trace, for example HandleSignal). Rules, each one printed as PASS/FAIL:
  one-trace         all of them share one trace id
  roots             exactly one span has no parent (StartWorkflow:<type>; with --no-start-workflow,
                    RunWorkflow:<type>)
  hierarchy         RunWorkflow under StartWorkflow, StartActivity under RunWorkflow, RunActivity under
                    StartActivity, and every llm or tool span under a RunActivity span
  llm-spans         with --llm-spans N: exactly N spans of type llm
  expect            with --expect NAME=COUNT: exactly COUNT spans with that name (a retried activity
                    has one RunActivity span per attempt)
  errors            with --errors NAME=COUNT: exactly COUNT spans with that name have status ERROR
Exit 0 when every rule passes, 1 otherwise. Prints span names and counts, never content.
"""
import argparse
import json
import sys
from collections import Counter


def attrs(span: dict) -> dict:
    a = span.get("attrs_string") or {}
    return a if isinstance(a, dict) else {}


def workflow_spans(spans: list[dict], workflow_id: str | None, ignore: tuple[str, ...] = ()) -> list[dict]:
    if workflow_id:
        spans = [s for s in spans if workflow_id in (attrs(s).get("session.id"), attrs(s).get("temporalWorkflowID"))]
    return [s for s in spans if not s["name"].startswith(ignore)] if ignore else list(spans)


def prefix(name: str) -> str:
    return name.split(":", 1)[0]


def check(spans: list[dict], expect: dict[str, int], errors: dict[str, int], start_workflow: bool, llm: int | None):
    by_id = {s["id"]: s for s in spans}
    names = Counter(s["name"] for s in spans)
    traces = {s["trace_id"] for s in spans}
    roots = [s for s in spans if s.get("parent_span_id") not in by_id]
    want_root = "StartWorkflow" if start_workflow else "RunWorkflow"
    expected_parent = {"RunWorkflow": "StartWorkflow", "StartActivity": "RunWorkflow", "RunActivity": "StartActivity"}
    bad = []
    for s in spans:
        parent = by_id.get(s.get("parent_span_id"))
        kind = prefix(s["name"])
        if kind in expected_parent and parent is not None and prefix(parent["name"]) != expected_parent[kind]:
            bad.append(f"{s['name']} under {parent['name']}")
        if kind == "StartActivity" and parent is None:
            bad.append(f"{s['name']} has no parent")
        if kind == "RunWorkflow" and parent is None and start_workflow:
            bad.append(f"{s['name']} has no StartWorkflow parent")
        if (s.get("observation_type") or "").lower() in ("llm", "tool"):
            if parent is None or prefix(parent["name"]) != "RunActivity":
                bad.append(f"{s['name']} ({s['observation_type']}) is not under a RunActivity span")
    rules = [
        ("one-trace", len(traces) == 1, f"{len(traces)} trace(s), {len(spans)} spans"),
        ("roots", len(roots) == 1 and prefix(roots[0]["name"]) == want_root, f"root spans: {sorted(s['name'] for s in roots)}"),
        ("hierarchy", not bad and bool(spans), "ok" if not bad else "; ".join(bad)),
    ]
    if llm is not None:
        n = sum(1 for s in spans if (s.get("observation_type") or "").lower() == "llm")
        rules.append(("llm-spans", n == llm, f"{n} llm span(s), expected {llm}"))
    for name, want in expect.items():
        rules.append((f"expect {name}", names.get(name, 0) == want, f"{names.get(name, 0)} stored, expected {want}"))
    for name, want in errors.items():
        got = sum(1 for s in spans if s["name"] == name and s.get("status") == "ERROR")
        rules.append((f"errors {name}", got == want, f"{got} with status ERROR, expected {want}"))
    return {"spans": len(spans), "names": dict(names)}, rules


def parse_counts(items: list[str]) -> dict[str, int]:
    out = {}
    for item in items:
        name, _, count = item.rpartition("=")
        out[name] = int(count)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spans")
    ap.add_argument("--workflow")
    ap.add_argument("--ignore", action="append", default=[], metavar="NAME_PREFIX")
    ap.add_argument("--expect", action="append", default=[], metavar="NAME=COUNT")
    ap.add_argument("--errors", action="append", default=[], metavar="NAME=COUNT")
    ap.add_argument("--no-start-workflow", action="store_true")
    ap.add_argument("--llm-spans", type=int)
    a = ap.parse_args()
    with open(a.spans) as f:
        spans = workflow_spans(json.load(f), a.workflow, tuple(a.ignore))
    summary, rules = check(spans, parse_counts(a.expect), parse_counts(a.errors), not a.no_start_workflow, a.llm_spans)
    print(json.dumps(summary))
    for name, ok, detail in rules:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    passed = all(ok for _, ok, _ in rules)
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
