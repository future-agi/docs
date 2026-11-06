#!/usr/bin/env python3
"""Scan EVERY stored column of a project's spans for marker strings.

Reads the local Future AGI stack (docker exec into the ClickHouse and Postgres
containers): all columns of the ClickHouse `spans` table (incl. resource_attrs,
span_events, attributes_extra, input/output) and every Postgres `tracer_*` row
that carries the project id. Exits 1 if expectation is violated.

  scan_privacy.py --project NAME --absent MARK [--absent MARK ...] [--present MARK ...]
"""
import argparse
import json
import subprocess
import sys
import time

CH_C = "th8103-e2e-clickhouse-1"
PG_C = "th8103-e2e-postgres-1"


def sh(cmd):
    # the shared local ClickHouse can hit its memory cap under load; retry a few times
    for attempt in range(6):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if not r.returncode:
            return r.stdout
        time.sleep(20)
    raise SystemExit(f"command failed: {cmd[:4]} {r.stderr[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--absent", action="append", default=[])
    ap.add_argument("--present", action="append", default=[])
    ap.add_argument("--since", default="", help="only rows with start_time >= this (UTC 'YYYY-MM-DD HH:MM:SS')")
    ap.add_argument("--ch", default=CH_C)
    ap.add_argument("--pg", default=PG_C)
    a = ap.parse_args()
    name = a.project.replace("'", "''")
    pids = [r.split("|")[0] for r in sh(["docker", "exec", a.pg, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc",
            f"select id from tracer_project where name='{name}' and not deleted"]).split() if r]
    if not pids:
        raise SystemExit("project not found")
    ids = ",".join(f"'{p}'" for p in pids)
    since = f" AND start_time >= '{a.since}'" if a.since else ""
    ch_rows = sh(["docker", "exec", a.ch, "clickhouse-client", "-q",
                  f"SELECT * FROM spans FINAL WHERE project_id IN ({ids}){since} FORMAT JSONEachRow"])
    blobs = {"clickhouse.spans": ch_rows}
    tables = sh(["docker", "exec", a.pg, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc",
                 "select table_name from information_schema.columns where column_name='project_id' and table_name like 'tracer%'"]).split()
    for t in tables:
        out = sh(["docker", "exec", a.pg, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc",
                  f"select row_to_json(x) from {t} x where project_id in ({ids})"])
        if out.strip():
            blobs["postgres." + t] = out
    n_rows = len([l for l in ch_rows.splitlines() if l.strip()])
    print(f"scanned clickhouse.spans rows={n_rows} + postgres tables with rows={[k for k in blobs if k.startswith('postgres')]}")
    bad = 0
    for m in a.absent:
        hits = [k for k, v in blobs.items() if m in v]
        print(f"ABSENT  {m!r}: {'FOUND in ' + str(hits) if hits else 'not found in any column'}")
        bad += bool(hits)
    for m in a.present:
        hits = [k for k, v in blobs.items() if m in v]
        print(f"PRESENT {m!r}: {'found in ' + str(hits) if hits else 'MISSING'}")
        bad += not hits
    print("PRIVACY_SCAN", "FAIL" if bad else "PASS")
    sys.exit(1 if bad else 0)


main()
