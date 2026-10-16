#!/usr/bin/env python3
"""Scan every stored row of a Future AGI project for strings that must (or must not) be there.

For the privacy proof on a self-hosted Future AGI that runs in Docker. It finds every ClickHouse and
Postgres table that has a project_id column, dumps ALL columns of the rows of one project (attributes,
resource attributes, span events, status message, input, output, metadata, tags, overflow JSON, end
users, sessions), and counts how often each needle occurs. Wire-tap files (what an exporter sent) can be
added with --wire.

  scan_local_stack.py --project my-project --needle MARKER --needle home=/Users/me --wire wire.jsonl

A needle can be written LABEL=VALUE (LABEL is lowercase letters, digits and underscores); the output
then shows the label and never the value.

Exit status: 0 when no needle is found (with --expect-found: when every needle is found), 1 otherwise,
2 when the project has no rows, 3 when a table could not be read (no verdict: a failed read is never reported as
"not found"). Only reads. Prints counts and table names, never row contents.
Containers default to the TH-8103 local stack; change them with FI_PG_CONTAINER and FI_CH_CONTAINER.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

PG_CONTAINER = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH_CONTAINER = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")


def run(cmd):
    # Some tables hold binary columns; decode leniently so one odd byte cannot hide the rest.
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


class ScanIncomplete(Exception):
    """A table could not be read. An absent-needle result would mean nothing, so the scan stops."""


def _query(cmd, what, tries=4):
    for attempt in range(tries):
        out = run(cmd)
        if out.returncode == 0:
            return out.stdout
        time.sleep(3 * (attempt + 1))  # the shared stack answers MEMORY_LIMIT_EXCEEDED under load; wait and retry
    raise ScanIncomplete(f"{what}: {out.stderr.strip()[:160]}")


def pg(sql, what="postgres query"):
    return _query(["docker", "exec", PG_CONTAINER, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc", sql], what)


def ch(sql, what="clickhouse query"):
    return _query(["docker", "exec", CH_CONTAINER, "clickhouse-client", "-q", sql], what)


def project_ids(name):
    safe = name.replace("'", "''")
    return [r.strip() for r in pg(f"select id from tracer_project where name='{safe}' and not deleted").splitlines() if r.strip()]


def main():
    try:
        return scan()
    except ScanIncomplete as exc:
        print(f"SCAN INCOMPLETE, no verdict: {exc}")
        return 3


def scan():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--needle", action="append", required=True)
    ap.add_argument("--wire", action="append", default=[], help="also scan a wire_tap.py output file")
    ap.add_argument("--ignore-case", action="store_true")
    ap.add_argument("--expect-found", action="store_true", help="every needle must be present")
    ap.add_argument("--json", help="write the per-table counts here")
    a = ap.parse_args()

    ids = project_ids(a.project)
    if not ids:
        print(f"no project named {a.project!r}")
        return 2
    id_list = ",".join(f"'{i}'" for i in ids)

    blobs = {}
    # Storage tables only: dictionaries, materialized views and the Aggregating/Summing rollups hold counts and
    # lookups derived from these tables, not text.
    ch_tables = [t for t in ch(
        "SELECT t.name FROM system.tables t WHERE t.database='default' AND t.engine LIKE '%MergeTree' "
        "AND t.engine NOT IN ('AggregatingMergeTree','SummingMergeTree') "
        "AND t.name IN (SELECT DISTINCT table FROM system.columns WHERE database='default' AND name='project_id')"
    ).split() if t]
    pg_tables = [t for t in pg(
        "select table_name from information_schema.columns where table_schema='public' and column_name='project_id'"
    ).split() if t]

    def dump_ch(table):
        return f"clickhouse.{table}", ch(f"SELECT * FROM {table} WHERE project_id IN ({id_list}) FORMAT JSONEachRow", f"clickhouse.{table}")

    def dump_pg(table):
        return f"postgres.{table}", pg(f"select row_to_json(t) from {table} t where project_id in ({id_list})", f"postgres.{table}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(dump_ch, t) for t in sorted(ch_tables)] + [pool.submit(dump_pg, t) for t in sorted(pg_tables)]
        for job in jobs:
            name, text = job.result()
            if text.strip():
                blobs[name] = text
    for path in a.wire:
        with open(path) as f:
            blobs[f"wire.{os.path.basename(path)}"] = f.read()

    rows_total = sum(b.count("\n") for b in blobs.values())
    print(f"project {a.project!r}: scanned {len(blobs)} non-empty table(s) of {len(ch_tables)} ClickHouse + {len(pg_tables)} Postgres candidates, {rows_total} row(s): {sorted(blobs)}")
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
        esc = needle.replace("/", "\\/")  # JSON may escape "/"
        if esc != needle:
            for t, b in hay.items():
                if esc in b:
                    hits[t] = hits.get(t, 0) + b.count(esc)
        shown = label or (needle if len(needle) <= 24 else needle[:10] + "..." + needle[-6:])
        report[shown] = hits
        print(f"  needle {shown!r}: {'FOUND ' + json.dumps(hits) if hits else 'not found'}")
        if a.expect_found != bool(hits):
            bad = True
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"project": a.project, "tables": sorted(blobs), "rows": rows_total, "needles": report}, f, indent=1)
    print("RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
