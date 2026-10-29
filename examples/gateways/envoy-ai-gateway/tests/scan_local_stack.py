#!/usr/bin/env python3
"""Scan every stored column of a self-hosted Future AGI stack for marker strings.

Used by run_e2e.sh for the privacy proof. Dumps whole rows (all columns, incl. resource
attributes and span events) of the ClickHouse `spans`, `traces`, `trace_sessions` tables and the
Postgres tracer_* tables for one project, then counts occurrences of each marker.
Defaults match the th8103 local docker stack; override with env CH_CONTAINER / PG_CONTAINER.
usage: scan_local_stack.py <project-name> <marker> [<marker> ...]   (exit 1 when any marker is found)
"""
import os, subprocess, sys

CH = ["docker", "exec", os.environ.get("CH_CONTAINER", "th8103-e2e-clickhouse-1"), "clickhouse-client", "-q"]
PG = ["docker", "exec", os.environ.get("PG_CONTAINER", "th8103-e2e-postgres-1"), "psql", "-U", "futureagi", "-d", "futureagi", "-Atc"]


def run(cmd, sql):
    r = subprocess.run(cmd + [sql], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"query failed: {r.stderr[:300]}")
    return r.stdout


def main():
    project, markers = sys.argv[1], sys.argv[2:]
    if not markers:
        raise SystemExit(__doc__)
    pid = run(PG, f"select id from tracer_project where name='{project.replace(chr(39), '')}' and not deleted").split()[0]
    dumps = {}
    for t in ("spans", "traces", "trace_sessions", "trace_session"):
        try:
            dumps[f"ch.{t}"] = run(CH, f"SELECT * FROM {t} WHERE project_id = '{pid}' FORMAT JSONEachRow")
        except SystemExit:
            dumps[f"ch.{t}"] = ""  # table without project_id column
    for t in ("tracer_project", "tracer_trace", "tracer_observation_span", "trace_session", "tracer_trace_session"):
        try:
            col = "id" if t == "tracer_project" else "project_id"
            dumps[f"pg.{t}"] = run(PG, f"select row_to_json(x) from {t} x where {col}='{pid}'")
        except SystemExit:
            pass
    bad = 0
    for name, text in dumps.items():
        print(f"scanned {name}: {len(text)} bytes")
    for m in markers:
        hits = {n: t.count(m) for n, t in dumps.items() if m in t}
        print(f"marker {m!r}: {'FOUND ' + str(hits) if hits else 'absent from all scanned tables'}")
        bad += bool(hits)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
