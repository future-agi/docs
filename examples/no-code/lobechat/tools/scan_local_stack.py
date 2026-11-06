#!/usr/bin/env python3
"""Scan every stored row of one Future AGI project for strings that must (or must not) be there.

Privacy proof for a self-hosted Future AGI stack that runs in Docker. The script finds every ClickHouse
and Postgres table that has a project_id column, dumps ALL columns of the rows that belong to the
project (span attributes, resource attributes, span events, status message, input, output, metadata,
sessions, end users) and counts how often each needle occurs.

  scan_local_stack.py --project my-project --needle MARKER --needle home=/Users/me
  scan_local_stack.py --project my-project --keys keys.json     # attribute-key inventory only

A needle may be written LABEL=VALUE (LABEL is lowercase letters, digits and underscores); the output then
shows the label, never the value. Exit status: 0 when no needle is found (with --expect-found: when every
needle is found), 1 otherwise, 2 when the project has no span rows, 3 when a table could not be read
(a failed read is never reported as "not found"). Only reads. Prints counts and table names, never row
contents. Containers default to the TH-8103 local stack; override with FI_PG_CONTAINER / FI_CH_CONTAINER.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

PG_CONTAINER = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH_CONTAINER = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")
LABELLED = re.compile(r"^([a-z0-9_]+)=(.+)$")


class ScanIncomplete(Exception):
    """A table could not be read. An absent-needle verdict would mean nothing, so the scan stops."""


def _query(cmd, what, tries=4):
    out = None
    for attempt in range(tries):
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if out.returncode == 0:
            return out.stdout
        time.sleep(3 * (attempt + 1))  # the shared stack answers MEMORY_LIMIT_EXCEEDED under load
    raise ScanIncomplete(f"{what}: {out.stderr.strip()[:160]}")


def pg(sql, what="postgres query"):
    cmd = ["docker", "exec", PG_CONTAINER, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc", sql]
    return _query(cmd, what)


def ch(sql, what="clickhouse query"):
    return _query(["docker", "exec", CH_CONTAINER, "clickhouse-client", "-q", sql], what)


def parse_needle(raw):
    """Return (label, value). The label is what gets printed; without one a short preview is shown."""
    m = LABELLED.match(raw)
    if m:
        return m.group(1), m.group(2)
    preview = raw if len(raw) <= 24 else raw[:10] + "..." + raw[-6:]
    return preview, raw


def count_needle(blobs, needle, ignore_case=False):
    """Occurrences of needle per table, also matching the JSON-escaped form ("/" written as "\\/")."""
    hits = {}
    variants = {needle}
    if "/" in needle:
        variants.add(needle.replace("/", "\\/"))
    for table, blob in blobs.items():
        hay = blob.lower() if ignore_case else blob
        n = sum(hay.count(v.lower() if ignore_case else v) for v in variants)
        if n:
            hits[table] = n
    return hits


def attribute_keys(span_rows):
    """Sorted attribute and resource-attribute keys seen on the stored spans (for the conformance table)."""
    span_keys, resource_keys, names = set(), set(), set()
    for row in span_rows:
        names.add(row.get("name", ""))
        for col, target in (("attributes", span_keys), ("span_attributes", span_keys),
                            ("resource_attributes", resource_keys), ("resource_attrs", resource_keys)):
            val = row.get(col)
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except ValueError:
                    val = None
            if isinstance(val, dict):
                target.update(val.keys())
        for col in ("attrs_string", "attrs_number", "attrs_bool"):
            val = row.get(col)
            if isinstance(val, dict):
                span_keys.update(val.keys())
    return {"span_names": sorted(n for n in names if n), "span_attribute_keys": sorted(span_keys),
            "resource_attribute_keys": sorted(resource_keys)}


def project_ids(name):
    safe = name.replace("'", "''")
    rows = pg(f"select id from tracer_project where name='{safe}' and not deleted")
    return [r.strip() for r in rows.splitlines() if r.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--needle", action="append", default=[])
    ap.add_argument("--ignore-case", action="store_true")
    ap.add_argument("--expect-found", action="store_true", help="every needle must be present")
    ap.add_argument("--json", help="write per-table counts here")
    ap.add_argument("--keys", help="write the attribute-key inventory of the stored spans here")
    a = ap.parse_args(argv)
    try:
        return scan(a)
    except ScanIncomplete as exc:
        print(f"SCAN INCOMPLETE, no verdict: {exc}")
        return 3


def scan(a):
    ids = project_ids(a.project)
    if not ids:
        print(f"no project named {a.project!r}")
        return 2
    id_list = ",".join(f"'{i}'" for i in ids)
    ch_tables = [t for t in ch(
        "SELECT t.name FROM system.tables t WHERE t.database='default' AND t.engine LIKE '%MergeTree' "
        "AND t.engine NOT IN ('AggregatingMergeTree','SummingMergeTree') "
        "AND t.name IN (SELECT DISTINCT table FROM system.columns WHERE database='default' AND name='project_id')"
    ).split() if t]
    pg_tables = [t for t in pg(
        "select table_name from information_schema.columns where table_schema='public' and column_name='project_id'"
    ).split() if t]
    blobs = {}
    for t in sorted(ch_tables):
        text = ch(f"SELECT * FROM {t} WHERE project_id IN ({id_list}) FORMAT JSONEachRow", f"clickhouse.{t}")
        if text.strip():
            blobs[f"clickhouse.{t}"] = text
    for t in sorted(pg_tables):
        text = pg(f"select row_to_json(x) from {t} x where project_id in ({id_list})", f"postgres.{t}")
        if text.strip():
            blobs[f"postgres.{t}"] = text
    rows = sum(b.count("\n") for b in blobs.values())
    print(f"project {a.project!r}: {len(blobs)} non-empty table(s) of {len(ch_tables)} ClickHouse + "
          f"{len(pg_tables)} Postgres candidates, {rows} row(s): {sorted(blobs)}")
    if "clickhouse.spans" not in blobs:
        print("no span rows stored for this project")
        return 2
    if a.keys:
        span_rows = [json.loads(line) for line in blobs["clickhouse.spans"].splitlines() if line.strip()]
        with open(a.keys, "w") as f:
            json.dump(attribute_keys(span_rows), f, indent=1)
        print(f"attribute-key inventory written to {a.keys}")
    report, bad = {}, False
    for raw in a.needle:
        label, needle = parse_needle(raw)
        hits = count_needle(blobs, needle, a.ignore_case)
        report[label] = hits
        print(f"  needle {label!r}: {'FOUND ' + json.dumps(hits) if hits else 'not found'}")
        if a.expect_found != bool(hits):
            bad = True
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"project": a.project, "tables": sorted(blobs), "rows": rows, "needles": report}, f, indent=1)
    if a.needle:
        print("RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
