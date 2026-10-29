#!/usr/bin/env python3
"""Privacy proof for a self-hosted Future AGI that runs in Docker: count a marker across EVERY stored column.

Finds every ClickHouse MergeTree table and every Postgres table that has a `project_id` column, dumps all
columns of the rows that belong to one project (span attributes, resource attributes, span events, status
message, input, output, metadata, sessions ...) and counts each needle. Optionally adds wire files (what the
exporter sent) to the haystack.

  scan_stored.py --project my-project --needle marker=ZQX123 [--needle ...] [--wire wire.json] [--expect-found]
                 [--trace <32-hex trace id> ...] [--wait 180]

--trace makes the scan wait (up to --wait seconds) until those traces are stored, so a scan that runs
before ingestion finished cannot pass by accident.

LABEL=VALUE needles print only the label. Exit 0 when no needle is found (with --expect-found: when all are),
1 otherwise, 2 when the project has no stored spans, 3 when a table could not be read (no verdict).
Read-only. Prints table names and counts, never row contents.
Containers: FI_PG_CONTAINER (default th8103-e2e-postgres-1), FI_CH_CONTAINER (default th8103-e2e-clickhouse-1).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

PG = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")


class Incomplete(Exception):
    pass


def _run(cmd, what):
    for attempt in range(4):
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if out.returncode == 0:
            return out.stdout
        time.sleep(3 * (attempt + 1))  # the shared ClickHouse answers MEMORY_LIMIT_EXCEEDED under load
    raise Incomplete(f"{what}: {out.stderr.strip()[:160]}")


def pg(sql, what="postgres"):
    return _run(["docker", "exec", PG, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc", sql], what)


def ch(sql, what="clickhouse"):
    return _run(["docker", "exec", CH, "clickhouse-client", "-q", sql], what)


def count(hay, needle):
    n = hay.count(needle)
    esc = needle.replace("/", "\\/")  # JSON may escape "/"
    return n + (hay.count(esc) if esc != needle else 0)


def as_uuid(trace_id):
    t = trace_id.replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", t):
        raise SystemExit(f"not a trace id: {trace_id!r}")
    return f"{t[:8]}-{t[8:12]}-{t[12:16]}-{t[16:20]}-{t[20:]}"


def parse_needle(raw):
    m = re.match(r"^([a-z0-9_]+)=(.+)$", raw)
    return (m.group(1), m.group(2)) if m else (raw if len(raw) <= 24 else raw[:8] + "...", raw)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--needle", action="append", required=True)
    ap.add_argument("--wire", action="append", default=[])
    ap.add_argument("--expect-found", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--trace", action="append", default=[])
    ap.add_argument("--wait", type=int, default=180)
    a = ap.parse_args(argv)
    try:
        safe = a.project.replace("'", "''")
        deadline = time.time() + a.wait
        while True:  # the project row is created by the first ingested batch
            ids = [r for r in pg(f"select id from tracer_project where name='{safe}' and not deleted").split() if r]
            if ids or not a.trace or time.time() > deadline:
                break
            time.sleep(5)
        if not ids:
            print(f"no project named {a.project!r}")
            return 2
        id_list = ",".join(f"'{i}'" for i in ids)
        want = {as_uuid(t) for t in a.trace}
        while want:
            got = set(ch(
                f"SELECT DISTINCT toString(trace_id) FROM spans WHERE project_id IN ({id_list}) "
                f"AND trace_id IN ({','.join(repr(t) for t in sorted(want))})", "clickhouse.spans (wait)"
            ).split())
            if want <= got:
                break
            if time.time() > deadline:
                print(f"SCAN INCOMPLETE, no verdict: {len(want - got)} of {len(want)} trace(s) not stored after {a.wait}s")
                return 3
            time.sleep(5)
        ch_tables = sorted(t for t in ch(
            "SELECT name FROM system.tables WHERE database='default' AND engine LIKE '%MergeTree' "
            "AND engine NOT IN ('AggregatingMergeTree','SummingMergeTree') "
            "AND name IN (SELECT DISTINCT table FROM system.columns WHERE database='default' AND name='project_id')"
        ).split() if t)
        pg_tables = sorted(set(t for t in pg(
            "select table_name from information_schema.columns where table_schema='public' and column_name='project_id'"
        ).split() if t))
        blobs = {}
        for t in ch_tables:
            text = ch(f"SELECT * FROM {t} WHERE project_id IN ({id_list}) FORMAT JSONEachRow", f"clickhouse.{t}")
            if text.strip():
                blobs[f"clickhouse.{t}"] = text
        for t in pg_tables:
            text = pg(f"select row_to_json(x) from {t} x where project_id in ({id_list})", f"postgres.{t}")
            if text.strip():
                blobs[f"postgres.{t}"] = text
    except Incomplete as exc:
        print(f"SCAN INCOMPLETE, no verdict: {exc}")
        return 3
    for path in a.wire:
        with open(path, encoding="utf-8") as f:
            blobs[f"wire.{os.path.basename(path)}"] = f.read()
    rows = sum(b.count("\n") for b in blobs.values())
    print(f"project {a.project!r}: {len(blobs)} non-empty of {len(ch_tables)} ClickHouse + {len(pg_tables)} Postgres tables, {rows} rows: {sorted(blobs)}")
    if "clickhouse.spans" not in blobs:
        print("no span rows stored for this project")
        return 2
    report, bad = {}, False
    for raw in a.needle:
        label, needle = parse_needle(raw)
        hits = {t: count(b, needle) for t, b in blobs.items() if count(b, needle)}
        report[label] = hits
        print(f"  needle {label!r}: {'FOUND ' + json.dumps(hits) if hits else 'not found'}")
        if a.expect_found != bool(hits):
            bad = True
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"project": a.project, "tables": sorted(blobs), "rows": rows, "needles": report}, f, indent=1)
    print("RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
