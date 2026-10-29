#!/usr/bin/env python3
"""Check specific traces in the local Future AGI store (ClickHouse `spans`, via docker exec).

  check_traces.py --project NAME --present TRACE[:CALLER_SPAN] ... --absent TRACE ... --error TRACE ...

--present  the trace landed in the project; with :CALLER_SPAN the root (SERVER) span's parent must be
           that span id, i.e. the Gateway joined the caller's W3C trace
--absent   no span of that trace was stored anywhere (any project)
--root     the trace landed in the project and has a root span (no parent), so it is listed in Observe
--error    at least one span of that trace has status ERROR
Prints one line per trace and exits 1 on any failed expectation.
"""
import argparse
import json
import os
import subprocess
import sys
import time

CH = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")
PG = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")


def uuid_form(h):
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def ch(sql):
    for _ in range(6):   # the shared local ClickHouse can hit its memory cap; retry
        r = subprocess.run(["docker", "exec", CH, "clickhouse-client", "-q", sql + " FORMAT JSONEachRow"],
                           capture_output=True, text=True)
        if not r.returncode:
            return [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
        time.sleep(20)
    raise SystemExit("clickhouse error: " + r.stderr[:300])


def project_ids(name):
    n = name.replace("'", "''")
    r = subprocess.run(["docker", "exec", PG, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc",
                        f"select id from tracer_project where name='{n}' and not deleted"], capture_output=True, text=True)
    return [x for x in r.stdout.split() if x]


def spans(trace):
    return ch("SELECT name, observation_type, status, parent_span_id, id, toString(project_id) AS project_id "
              f"FROM spans FINAL WHERE trace_id='{uuid_form(trace)}' AND is_deleted = 0 ORDER BY start_time")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--present", action="append", default=[])
    ap.add_argument("--absent", action="append", default=[])
    ap.add_argument("--root", action="append", default=[])
    ap.add_argument("--error", action="append", default=[])
    ap.add_argument("--json", help="write the rows of every --present trace here")
    ap.add_argument("--wait", type=int, default=90, help="seconds to wait for the --present traces")
    a = ap.parse_args()
    end = time.time() + a.wait
    while time.time() < end and not all(spans(i.partition(":")[0]) for i in a.present + a.root):
        time.sleep(5)
    pids = set(project_ids(a.project))
    bad = 0
    dump = {}
    for item in a.present:
        trace, _, caller = item.partition(":")
        rows = spans(trace)
        dump[trace] = rows
        in_proj = [r for r in rows if r["project_id"] in pids]
        msg = f"PRESENT {trace}: {len(in_proj)} spans in project"
        ok = bool(in_proj) and len(in_proj) == len(rows)
        if caller:
            roots = [r for r in in_proj if r["parent_span_id"] and r["parent_span_id"] not in {x["id"] for x in in_proj}]
            joined = any(r["parent_span_id"].replace("-", "").endswith(caller) for r in roots)
            msg += f", root parent = caller span {caller}: {'yes' if joined else 'NO'}"
            ok = ok and joined
        names = sorted({r["name"] for r in in_proj})
        print(msg, "|", ", ".join(names)[:300], "|", "OK" if ok else "FAIL")
        bad += not ok
    for trace in a.root:
        rows = [r for r in spans(trace) if r["project_id"] in pids]
        roots = [r["name"] for r in rows if not r["parent_span_id"]]
        print(f"ROOT    {trace}: {len(rows)} spans in project, root span = {roots} |", "OK" if roots else "FAIL")
        bad += not roots
    for trace in a.absent:
        rows = spans(trace)
        print(f"ABSENT  {trace}: {len(rows)} spans stored |", "OK" if not rows else "FAIL")
        bad += bool(rows)
    for trace in a.error:
        rows = spans(trace)
        errs = [r["name"] for r in rows if str(r["status"]).upper() == "ERROR"]
        print(f"ERROR   {trace}: ERROR spans = {errs} |", "OK" if errs else "FAIL")
        bad += not errs
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dump, f, indent=1, default=str)
    print("CHECK_TRACES", "FAIL" if bad else "PASS")
    sys.exit(1 if bad else 0)


main()
