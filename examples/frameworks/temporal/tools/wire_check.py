#!/usr/bin/env python3
"""Check a wire_tap.py capture: what the Temporal worker and starter really sent to Future AGI.

  wire_check.py wire.jsonl [--project NAME] [--expect NAME=COUNT ...] [--total N] [--allow-empty] [--allow-duplicates]

Rules, each one printed as PASS/FAIL:
  uncompressed   no request carried a Content-Encoding (the recipe sends plain bodies)
  key-headers    every request carried X-Api-Key and X-Secret-Key (and, when the tap knew the
                 expected values, they matched)
  project-name   every resource carried project_name (equal to --project when given)
  accepted       Future AGI answered 2xx to every request
  exactly-once   no (trace id, span id) pair was sent twice, so a replayed workflow was not exported again
  expect         with --expect NAME=COUNT: exactly COUNT spans of that name were sent
  total          with --total N: exactly N spans were sent in all
With --allow-empty, a capture without any request passes the header, project and status rules (an
exporter that had nothing to send sends no request).
Prints counts and span names only, never content. Exit 0 when every rule passes.
"""
import argparse
import json
import sys
from collections import Counter


def resource_attrs(rs: dict) -> dict:
    out = {}
    for a in rs.get("resource", {}).get("attributes", []):
        v = a.get("value", {})
        out[a["key"]] = next(iter(v.values()), None) if v else None
    return out


def spans_of(lines: list[dict]) -> list[dict]:
    spans = []
    for rec in lines:
        for rs in rec.get("body", {}).get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                spans.extend(ss.get("spans", []))
    return spans


def check(lines: list[dict], project: str | None, expect: dict[str, int], allow_duplicates: bool, allow_empty: bool, total: int | None):
    projects = Counter()
    for rec in lines:
        for rs in rec.get("body", {}).get("resourceSpans", []):
            projects[resource_attrs(rs).get("project_name")] += 1
    spans = spans_of(lines)
    names = Counter(s["name"] for s in spans)
    ids = Counter((s.get("traceId"), s.get("spanId")) for s in spans)
    dupes = sum(1 for c in ids.values() if c > 1)
    enc = sorted({r["content_encoding"] for r in lines if r.get("content_encoding")})
    keys = all(r.get("has_key_headers") for r in lines)
    match = [r["key_values_match"] for r in lines if "key_values_match" in r]
    statuses = Counter(r.get("status") for r in lines)
    empty_ok = allow_empty and not lines
    rules = [
        ("uncompressed", not enc, f"content-encodings seen: {enc}"),
        ("key-headers", empty_ok or (bool(lines) and keys and all(match)), f"present on all: {keys}; values checked on {len(match)}, all match: {all(match)}"),
        ("project-name", empty_ok or (bool(projects) and None not in projects and (project is None or set(projects) == {project})), f"{dict(projects)}"),
        ("accepted", empty_ok or (bool(lines) and all(200 <= (s or 0) < 300 for s in statuses)), f"statuses: {dict(statuses)}"),
        ("exactly-once", allow_duplicates or dupes == 0, f"{len(spans)} spans sent, {dupes} (trace id, span id) pair(s) sent more than once"),
    ]
    if total is not None:
        rules.append(("total", len(spans) == total, f"{len(spans)} spans sent, expected {total}"))
    for name, want in expect.items():
        rules.append((f"expect {name}", names.get(name, 0) == want, f"sent {names.get(name, 0)}, expected {want}"))
    return {"requests": len(lines), "spans": len(spans), "names": dict(names)}, rules


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wire")
    ap.add_argument("--project")
    ap.add_argument("--expect", action="append", default=[], metavar="NAME=COUNT")
    ap.add_argument("--allow-duplicates", action="store_true")
    ap.add_argument("--allow-empty", action="store_true")
    ap.add_argument("--total", type=int)
    a = ap.parse_args()
    expect = {}
    for item in a.expect:
        name, _, count = item.rpartition("=")
        expect[name] = int(count)
    with open(a.wire) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    summary, rules = check(lines, a.project, expect, a.allow_duplicates, a.allow_empty, a.total)
    print(json.dumps(summary))
    for name, ok, detail in rules:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    passed = all(ok for _, ok, _ in rules)
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
