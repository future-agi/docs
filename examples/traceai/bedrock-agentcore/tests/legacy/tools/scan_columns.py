#!/usr/bin/env python3
"""Count stored span rows of a self-hosted Future AGI project that contain a needle in ANY column.

    scan_columns.py PROJECT [LABEL=NEEDLE ...]

Reads the spans table (every column, including input, output, attribute maps, resource
attributes, span events and status message) of a self-hosted Future AGI through `docker exec`
into its ClickHouse and Postgres containers. Prints counts, never content. Always exits 0; the
caller compares the counts. Container names default to the local e2e stack and can be changed
with FI_CH_CONTAINER / FI_PG_CONTAINER.
"""
import os
import re
import subprocess
import sys
import time

CH = ["docker", "exec", os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1"), "clickhouse-client", "-q"]
PG = ["docker", "exec", os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1"),
      "psql", "-U", "futureagi", "-d", "futureagi", "-Atc"]


def ch(query):
    for _ in range(5):  # a shared ClickHouse can hit its memory cap: wait and retry
        out = subprocess.run(CH + [query], capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout.strip()
        time.sleep(20)
    return "error: " + out.stderr.strip()[:100]


def main():
    project = sys.argv[1].replace("'", "''")
    ids = subprocess.run(PG + [f"select id from tracer_project where name='{project}' and not deleted"],
                         capture_output=True, text=True).stdout.split()
    if not ids:
        print("project: absent")
        return 0
    in_list = ",".join(f"'{i}'" for i in ids)
    print("project rows: " + ch(f"SELECT count() FROM spans FINAL WHERE project_id IN ({in_list}) AND is_deleted = 0"))
    for raw in sys.argv[2:]:
        m = re.match(r"^([a-z0-9_]+)=(.+)$", raw)
        label, needle = (m.group(1), m.group(2)) if m else (raw[:8] + "...", raw)
        needle = needle.replace("\\", "\\\\").replace("'", "\\'")
        count = ch(f"SELECT count() FROM spans WHERE project_id IN ({in_list}) "
                   f"AND positionCaseInsensitive(toString(tuple(*)), '{needle}') > 0")
        print(f"{label}: rows containing it = {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
