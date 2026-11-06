#!/usr/bin/env python3
"""Summarize a wire_tap.py capture: what the collector really sent to Future AGI.

  wire_summary.py wire.jsonl [--project NAME]

Checks, each printed as PASS/FAIL:
  uncompressed     no request carried a Content-Encoding
  key-headers      every request carried X-Api-Key and X-Secret-Key (and, when the tap knew the
                   expected values, they matched)
  no-bearer        no request carried an Authorization header (a watsonx token is never forwarded)
  project-name     every resource carried project_name (equal to --project when given)
  accepted         Future AGI answered 2xx to every request
Prints counts and span names only, never attribute values.
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


def summarize(lines: list[dict], project: str | None) -> tuple[dict, list[tuple[str, bool, str]]]:
    services, names, projects = Counter(), Counter(), Counter()
    spans = 0
    for rec in lines:
        for rs in rec.get("body", {}).get("resourceSpans", []):
            attrs = resource_attrs(rs)
            projects[attrs.get("project_name")] += 1
            services[attrs.get("service.name") or "(none)"] += 1
            for ss in rs.get("scopeSpans", []):
                for s in ss.get("spans", []):
                    spans += 1
                    names[s["name"]] += 1
    enc = [r.get("content_encoding") for r in lines if r.get("content_encoding")]
    keys = all(r.get("has_key_headers") for r in lines)
    match = [r["key_values_match"] for r in lines if "key_values_match" in r]
    bearer = sum(1 for r in lines if "authorization" in r.get("header_names", []))
    statuses = Counter(r.get("status") for r in lines)
    rules = [
        ("uncompressed", not enc, f"content-encodings seen: {sorted(set(enc))}"),
        ("key-headers", bool(lines) and keys and all(match),
         f"present on all: {keys}; values checked on {len(match)}, all match: {all(match)}"),
        ("no-bearer", bearer == 0, f"requests with an Authorization header: {bearer}"),
        (
            "project-name",
            bool(projects) and None not in projects and (project is None or set(projects) == {project}),
            f"{dict(projects)}",
        ),
        ("accepted", bool(lines) and all(200 <= (s or 0) < 300 for s in statuses), f"statuses: {dict(statuses)}"),
    ]
    summary = {"requests": len(lines), "spans": spans, "services": dict(services), "span_names": dict(names)}
    return summary, rules


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wire")
    ap.add_argument("--project")
    a = ap.parse_args()
    with open(a.wire) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    summary, rules = summarize(lines, a.project)
    print(json.dumps(summary))
    for name, ok, detail in rules:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    passed = all(ok for _, ok, _ in rules)
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
