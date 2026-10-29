#!/usr/bin/env python3
"""Tenant check: in which projects does a string occur, across the WHOLE spans table?

Searches every project's rows of a self-hosted Future AGI's ClickHouse `spans` table (name,
input, output, status message, span events, string attributes, resource attributes, metadata,
tags, overflow JSON) and prints the matching project names with row counts.

  isolation_check.py --needle MARKER --only my-project       # PASS if found only there
  isolation_check.py --needle MARKER --nowhere               # PASS if found in no project

Container names: FI_PG_CONTAINER, FI_CH_CONTAINER.
"""
import argparse
import os
import subprocess
import sys
import time
from collections import Counter

PG = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")
COLUMNS = [
    "name", "input", "output", "status_message", "span_events", "tags", "attributes_extra",
    "toString(attrs_string)", "toString(resource_attrs)", "toString(metadata)",
]


def run(cmd: list[str], attempts: int = 6) -> str:
    # A busy ClickHouse can refuse a full-table read (MEMORY_LIMIT_EXCEEDED); wait and retry.
    for i in range(attempts):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout
        if i + 1 < attempts:
            time.sleep(20)
    raise SystemExit(f"query failed: {out.stderr[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--needle", required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--only")
    group.add_argument("--nowhere", action="store_true")
    a = ap.parse_args()
    needle = a.needle.replace("\\", "\\\\").replace("'", "\\'")
    # One column per query, single-threaded, small blocks: keeps memory low on a shared server.
    hits: Counter = Counter()
    for column in COLUMNS:
        rows = run(["docker", "exec", CH, "clickhouse-client", "-q",
                    f"SELECT toString(project_id), count() FROM spans WHERE position({column}, '{needle}') > 0 "
                    "GROUP BY project_id SETTINGS max_threads = 1, max_block_size = 2048 FORMAT TSV"])
        for line in rows.splitlines():
            pid, n = line.split("\t")
            hits[pid] = max(hits[pid], int(n))
    total = int(run(["docker", "exec", CH, "clickhouse-client", "-q", "SELECT count() FROM spans FORMAT TSV"]).strip() or 0)
    found = {}
    for pid, n in hits.items():
        name = run(["docker", "exec", PG, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc",
                    f"select name from tracer_project where id='{pid}'"]).strip() or pid
        found[name] = int(n)
    print(f"scanned {len(COLUMNS)} columns of {total} span rows across all projects; "
          f"needle found in (max rows per column): {found or 'no project'}")
    ok = (not found) if a.nowhere else (set(found) == {a.only})
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
