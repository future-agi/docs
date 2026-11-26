#!/usr/bin/env python3
"""Scan every stored row of a Future AGI project for strings that must not be there.

Used for the privacy proof on a self-hosted Future AGI that runs in Docker. It
dumps ALL columns (attributes, resource attributes, span events, status message,
input, output, metadata, tags, overflow JSON) of every table that has a
project_id column, for one project, and counts how many times each needle occurs.

  scan_local_stack.py --project my-project --needle MARKER --needle home=/Users/me \\
      --wire wire.jsonl

A needle can be written LABEL=VALUE (LABEL is lowercase letters, digits and underscores);
the output then shows the label instead of the value.

Exit status: 0 when no needle is found (or with --expect-found when every needle
is found), 1 otherwise, 2 when the project has no rows.

Containers default to the ones of the TH-8103 local stack and can be changed
with FI_PG_CONTAINER and FI_CH_CONTAINER. Only reads. Prints counts and table
names, never row contents.
"""
import argparse
import json
import os
import re
import subprocess
import sys

PG_CONTAINER = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH_CONTAINER = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")
PG_ARGS = ["psql", "-U", "futureagi", "-d", "futureagi", "-Atc"]

CH_TABLES = ["spans", "traces", "trace_session", "end_users", "trace_sessions"]
PG_TABLES = ["tracer_observation_span", "tracer_trace", "tracer_enduser", "trace_session"]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def pg(sql):
    out = run(["docker", "exec", PG_CONTAINER, *PG_ARGS, sql])
    return out.stdout if out.returncode == 0 else ""


def ch(sql):
    out = run(["docker", "exec", CH_CONTAINER, "clickhouse-client", "-q", sql])
    return out.stdout if out.returncode == 0 else ""


def project_ids(name):
    safe = name.replace("'", "''")
    rows = pg(f"select id from tracer_project where name='{safe}' and not deleted")
    return [r.strip() for r in rows.splitlines() if r.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--needle", action="append", required=True)
    ap.add_argument("--wire", action="append", default=[], help="also scan a wire_tap.py output file (what the exporter sent)")
    ap.add_argument("--ignore-case", action="store_true", help="match needles case-insensitively")
    ap.add_argument("--expect-found", action="store_true", help="opt-in check: every needle must be present")
    ap.add_argument("--json", help="write the per-table counts here")
    a = ap.parse_args()

    ids = project_ids(a.project)
    if not ids:
        print(f"no project named {a.project!r}")
        return 2
    id_list = ",".join(f"'{i}'" for i in ids)

    blobs = {}
    for table in CH_TABLES:
        cols = ch(f"SELECT name FROM system.columns WHERE database='default' AND table='{table}' AND name='project_id'")
        if not cols.strip():
            continue
        text = ch(f"SELECT * FROM {table} FINAL WHERE project_id IN ({id_list}) FORMAT JSONEachRow") or ch(
            f"SELECT * FROM {table} WHERE project_id IN ({id_list}) FORMAT JSONEachRow"
        )
        if text.strip():
            blobs[f"clickhouse.{table}"] = text
    for table in PG_TABLES:
        has = pg(
            "select 1 from information_schema.columns where table_schema='public' "
            f"and table_name='{table}' and column_name='project_id'"
        )
        if not has.strip():
            continue
        text = pg(f"select row_to_json(t) from {table} t where project_id in ({id_list})")
        if text.strip():
            blobs[f"postgres.{table}"] = text

    for path in a.wire:
        with open(path) as f:
            blobs[f"wire.{os.path.basename(path)}"] = f.read()

    rows_total = sum(b.count("\n") for b in blobs.values())
    print(f"project {a.project!r}: scanned {len(blobs)} non-empty table(s), {rows_total} row(s): {sorted(blobs)}")
    if "clickhouse.spans" not in blobs:
        print("no span rows stored for this project")
        return 2

    report, bad = {}, False
    for raw in a.needle:
        m = re.match(r"^([a-z0-9_]+)=(.+)$", raw)
        label, needle = (m.group(1), m.group(2)) if m else (None, raw)
        hay = {t: (b.lower() if a.ignore_case else b) for t, b in blobs.items()}
        needle = needle.lower() if a.ignore_case else needle
        hits = {t: b.count(needle) for t, b in hay.items() if needle in b}
        # JSON escapes "/" only sometimes; also look for the escaped form.
        esc = needle.replace("/", "\\/")
        if esc != needle:
            for t, b in hay.items():
                if esc in b:
                    hits[t] = hits.get(t, 0) + b.count(esc)
        shown = label or (needle if len(needle) <= 24 else needle[:10] + "..." + needle[-6:])
        report[shown] = hits
        print(f"  needle {shown!r}: {'FOUND ' + json.dumps(hits) if hits else 'not found'}")
        if a.expect_found and not hits:
            bad = True
        if not a.expect_found and hits:
            bad = True
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"project": a.project, "tables": sorted(blobs), "rows": rows_total, "needles": report}, f, indent=1)
    print("RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
