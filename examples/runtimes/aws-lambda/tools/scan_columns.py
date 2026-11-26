#!/usr/bin/env python3
"""Count stored span rows of a project that contain a needle in ANY column.

    scan_columns.py PROJECT NEEDLE [NEEDLE ...]        (needle written LABEL=VALUE is printed by its label)

Reads the local Future AGI ClickHouse (the spans table, every column, resource attributes and
span events included) and Postgres (project id) through docker exec. Prints counts, never content.
Exit 0 always; the caller compares the counts.
"""
import re
import subprocess
import time
import sys

CH = ["docker", "exec", "th8103-e2e-clickhouse-1", "clickhouse-client", "-q"]
PG = ["docker", "exec", "th8103-e2e-postgres-1", "psql", "-U", "futureagi", "-d", "futureagi", "-Atc"]


def main():
    project = sys.argv[1]
    ids = subprocess.run(PG + [f"select id from tracer_project where name='{project}' and not deleted"], capture_output=True, text=True).stdout.split()
    if not ids:
        print("project: absent")
        return 0
    in_list = ",".join(f"'{i}'" for i in ids)
    total = subprocess.run(CH + [f"SELECT count() FROM spans FINAL WHERE project_id IN ({in_list}) AND is_deleted = 0"], capture_output=True, text=True).stdout.strip()
    print(f"project rows: {total}")
    for raw in sys.argv[2:]:
        m = re.match(r"^([a-z0-9_]+)=(.+)$", raw)
        label, needle = (m.group(1), m.group(2)) if m else (raw[:8] + "...", raw)
        q = (f"SELECT count() FROM spans WHERE project_id IN ({in_list}) "
             f"AND positionCaseInsensitive(toString(tuple(*)), '{needle}') > 0")
        for _ in range(5):  # the shared ClickHouse can hit its memory cap: wait and retry
            out = subprocess.run(CH + [q], capture_output=True, text=True)
            if out.stdout.strip().isdigit():
                break
            time.sleep(20)
        print(f"{label}: rows containing it = {out.stdout.strip() or out.stderr.strip()[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
