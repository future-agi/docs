#!/usr/bin/env python3
"""Count how often given strings occur in everything a self-hosted Future AGI stored for a project.

Privacy proof helper for a Future AGI that runs in Docker. For one project it dumps every
column (span attributes, resource attributes, span events, status message, input, output,
metadata, overflow JSON) of every ClickHouse and Postgres table that has a project_id column,
and optionally wire captures from wire_tap.py, then counts each needle.

  scan_local_stack.py --project my-project --needle MARKER --needle home=/Users/me [--wire wire.jsonl]
  scan_local_stack.py --project my-project --needle MARKER --expect-found     # opt-in check

A needle written LABEL=VALUE is reported by its label, so secrets and paths are not printed.
Exit 0 when no needle is found (with --expect-found: when every needle is found), 1 otherwise,
2 when the project has no stored spans. Container names: FI_PG_CONTAINER, FI_CH_CONTAINER.
"""
import argparse
import json
import os
import re
import subprocess
import sys

PG_CONTAINER = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH_CONTAINER = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")


def _run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, capture_output=True)
    # Rollup tables hold binary aggregate states; decode leniently, content columns are UTF-8.
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else ""


def pg(sql: str) -> str:
    return _run(["docker", "exec", PG_CONTAINER, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc", sql])


def ch(sql: str) -> str:
    return _run(["docker", "exec", CH_CONTAINER, "clickhouse-client", "-q", sql])


def project_ids(name: str) -> list[str]:
    safe = name.replace("'", "''")
    return [r.strip() for r in pg(f"select id from tracer_project where name='{safe}' and not deleted").splitlines() if r.strip()]


def collect(ids: list[str]) -> dict[str, str]:
    id_list = ",".join(f"'{i}'" for i in ids)
    blobs = {}
    ch_tables = ch(
        "SELECT c.table FROM system.columns c JOIN system.tables t ON c.database = t.database AND c.table = t.name "
        "WHERE c.database = 'default' AND c.name = 'project_id' AND t.engine NOT IN ('MaterializedView', 'View') FORMAT TSV"
    ).split()
    for table in sorted(set(ch_tables)):
        text = ch(f"SELECT * FROM {table} WHERE project_id IN ({id_list}) FORMAT JSONEachRow")
        if text.strip():
            blobs[f"clickhouse.{table}"] = text
    pg_tables = pg(
        "select table_name from information_schema.columns where table_schema='public' and column_name='project_id'"
    ).split()
    for table in sorted(set(pg_tables)):
        text = pg(f"select row_to_json(t) from {table} t where project_id::text in ({id_list})")
        if text.strip():
            blobs[f"postgres.{table}"] = text
    return blobs


def count(blobs: dict[str, str], needle: str, ignore_case: bool) -> dict[str, int]:
    forms = {needle, needle.replace("/", "\\/"), json.dumps(needle)[1:-1]}
    hits = {}
    for name, blob in blobs.items():
        hay = blob.lower() if ignore_case else blob
        n = sum(hay.count(f.lower() if ignore_case else f) for f in forms if f)
        if n:
            hits[name] = n
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--needle", action="append", required=True)
    ap.add_argument("--wire", action="append", default=[])
    ap.add_argument("--ignore-case", action="store_true")
    ap.add_argument("--expect-found", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()

    ids = project_ids(a.project)
    blobs = collect(ids) if ids else {}
    if not any(k.startswith("clickhouse.spans") for k in blobs):
        print(f"project {a.project!r}: no stored spans")
        return 2
    for path in a.wire:
        with open(path) as f:
            blobs[f"wire.{os.path.basename(path)}"] = f.read()
    rows = sum(b.count("\n") for b in blobs.values())
    print(f"project {a.project!r}: {len(blobs)} non-empty source(s), {rows} row(s): {sorted(blobs)}")

    report, bad = {}, False
    for raw in a.needle:
        m = re.match(r"^([a-z0-9_]+)=(.+)$", raw)
        label, needle = (m.group(1), m.group(2)) if m else (raw if len(raw) <= 24 else raw[:8] + "...", raw)
        hits = count(blobs, needle, a.ignore_case)
        report[label] = hits
        print(f"  {label}: {'FOUND ' + json.dumps(hits) if hits else 'not found'}")
        bad |= (not hits) if a.expect_found else bool(hits)
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"project": a.project, "sources": sorted(blobs), "rows": rows, "needles": report}, f, indent=1)
    print("RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
