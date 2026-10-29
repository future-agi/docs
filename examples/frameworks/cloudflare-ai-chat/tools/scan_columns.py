#!/usr/bin/env python3
"""Count stored rows of a Future AGI project that contain a needle in ANY column of ANY table.

    scan_columns.py PROJECT [LABEL=NEEDLE ...]

Self-hosted Future AGI in Docker only. ClickHouse: every table with a project_id column (spans, traces,
sessions, rollups, the attribute catalog), each row rendered whole with toString(tuple(*)), so resource
attributes, span events, attributes, input/output and status messages are all included. Postgres: every
public table with a project_id column, each row rendered whole (row::text). Prints counts, never content.
Container names: FI_CH_CONTAINER / FI_PG_CONTAINER (defaults th8103-e2e-clickhouse-1 / th8103-e2e-postgres-1).
"""
import os
import re
import subprocess
import sys
import time

CHC = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")
PGC = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH = ["docker", "exec", CHC, "clickhouse-client", "-q"]
PG = ["docker", "exec", PGC, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc"]


def run(cmd, q, retries=5):
    for _ in range(retries):  # the shared ClickHouse can hit its memory cap: wait and retry
        out = subprocess.run(cmd + [q], capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout.strip()
        time.sleep(20)
    return "ERR " + out.stderr.strip()[:120]


def sql_str(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"


def main():
    project = sys.argv[1]
    ids = run(PG, f"select id from tracer_project where name={sql_str(project)} and not deleted").split()
    if not ids:
        print("project: absent")
        return 0
    in_list = ",".join(sql_str(i) for i in ids)
    ch_tables = [l.split("\t") for l in run(CH, "SELECT database, table FROM system.columns WHERE name='project_id' "
                "AND database NOT IN ('system') AND table NOT LIKE '%_mv' AND table NOT LIKE '%_dict' "
                "GROUP BY database, table ORDER BY database, table FORMAT TSV").splitlines() if l]
    pg_tables = [t for t in run(PG, "select table_name from information_schema.columns where table_schema='public' "
                 "and column_name='project_id' order by 1").split() if t]
    rows = run(CH, f"SELECT count() FROM spans FINAL WHERE project_id IN ({in_list}) AND is_deleted = 0")
    print(f"project rows: {rows}  (ClickHouse tables scanned: {len(ch_tables)}, Postgres tables scanned: {len(pg_tables)})")
    for raw in sys.argv[2:]:
        m = re.match(r"^([a-z0-9_]+)=(.+)$", raw)
        label, needle = (m.group(1), m.group(2)) if m else ("needle", raw)
        total, where = 0, []
        for db, table in ch_tables:
            n = run(CH, f"SELECT count() FROM `{db}`.`{table}` WHERE toString(project_id) IN ({in_list}) "
                    f"AND positionCaseInsensitive(toString(tuple(*)), {sql_str(needle)}) > 0")
            if not n.isdigit():
                where.append(f"{db}.{table}:{n}")
                total = -1 if total == 0 else total
                continue
            if int(n):
                total = max(total, 0) + int(n)
                where.append(f"{db}.{table}={n}")
        for table in pg_tables:
            n = run(PG, f"select count(*) from \"{table}\" t where project_id::text in ({in_list}) "
                    f"and t::text ilike {sql_str('%' + needle.replace('%', chr(92) + '%') + '%')}")
            if not n.isdigit():
                where.append(f"pg.{table}:{n}")
                continue
            if int(n):
                total = max(total, 0) + int(n)
                where.append(f"pg.{table}={n}")
        print(f"{label}: rows containing it = {total}" + (f"  [{', '.join(where)}]" if where else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
