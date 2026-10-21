#!/usr/bin/env python3
"""Check what a self-hosted Future AGI stored for one Observe project after the LibreChat test run.

Reads the project row from Postgres and the spans from ClickHouse (the tables the Observe UI reads), via
`docker exec` into the stack's containers, and asserts the shape the recipe promises:

  check_spans.py --project librechat-e2e --model gpt-6-luna --expect-error --expect-backend --json out.json

  - agent runs: AGENT, LLM and TOOL spans; LLM spans carry the model and token counts; spans carry a
    session (the LibreChat conversation id) and an end user (LibreChat's internal user id)
  - --expect-error: at least one span with status ERROR (the provider failure turn)
  - --expect-backend: LibreChat's own backend spans (the chat POST and the SSE stream span)

Exit 0 when every check passes, 1 when one fails, 2 when nothing is stored for the project.
Containers default to the self-hosted Docker Compose names (project `futureagi`); override with
FI_PG_CONTAINER / FI_CH_CONTAINER.
"""
import argparse
import json
import os
import subprocess
import sys
import time

PG_CONTAINER = os.environ.get("FI_PG_CONTAINER", "futureagi-postgres-1")
CH_CONTAINER = os.environ.get("FI_CH_CONTAINER", "futureagi-clickhouse-1")
COLUMNS = ("trace_id, id, parent_span_id, name, observation_type, status, status_message, model, "
           "prompt_tokens, completion_tokens, total_tokens, toString(trace_session_id) AS session, "
           "toString(end_user_id) AS end_user, attrs_string")


def pg(sql):
    cmd = ["docker", "exec", PG_CONTAINER, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc", sql]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def ch_rows(sql):
    for attempt in range(4):
        out = subprocess.run(["docker", "exec", CH_CONTAINER, "clickhouse-client", "-q", sql + " FORMAT JSONEachRow"],
                             capture_output=True, text=True)
        if out.returncode == 0:
            return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]
        time.sleep(3 * (attempt + 1))
    raise SystemExit(f"clickhouse error: {out.stderr[:200]}")


def evaluate(spans, model=None, expect_error=False, expect_backend=False):
    """Pure check over stored span rows. Returns (checks, summary)."""
    kinds = {}
    for s in spans:
        kinds[s["observation_type"]] = kinds.get(s["observation_type"], 0) + 1
    llm = [s for s in spans if s["observation_type"] == "llm"]
    tools = [s for s in spans if s["observation_type"] == "tool"]
    agent_spans = [s for s in spans if s["observation_type"] in ("agent", "llm", "tool", "chain")]
    names = {s["name"] for s in spans}
    checks = {
        "agent span": any(s["observation_type"] == "agent" for s in spans),
        "llm span": bool(llm),
        "tool span with tool.name": any((s.get("attrs_string") or {}).get("tool.name") for s in tools),
        "llm model set": bool(llm) and all(s["model"] for s in llm if s["status"] != "ERROR"),
        "llm tokens set": any(s["prompt_tokens"] > 0 and s["completion_tokens"] > 0 for s in llm),
        "session on agent spans": bool(agent_spans) and all(s["session"] not in ("", None, "\\N")
                                                            for s in agent_spans),
        "end user on agent spans": bool(agent_spans) and all(s["end_user"] not in ("", None, "\\N")
                                                             for s in agent_spans),
    }
    if model:
        checks[f"model == {model}"] = any(s["model"] == model for s in llm)
    if expect_error:
        checks["ERROR span"] = any(s["status"] == "ERROR" for s in spans)
    if expect_backend:
        checks["backend chat POST span"] = "POST /api/agents/chat/:endpoint" in names
        checks["backend SSE stream span"] = "librechat.sse.stream" in names
        checks["no parentless background database spans"] = not any(
            s["name"].startswith("mongoose.") and not s["parent_span_id"] for s in spans)
    summary = {
        "spans": len(spans),
        "traces": len({s["trace_id"] for s in spans}),
        "kinds": kinds,
        "sessions": len({s["session"] for s in agent_spans}),
        "errors": [{"name": s["name"], "status_message": s["status_message"]} for s in spans
                   if s["status"] == "ERROR"],
        "llm": [{"model": s["model"], "prompt_tokens": s["prompt_tokens"],
                 "completion_tokens": s["completion_tokens"]} for s in llm],
        "tools": sorted({(s.get("attrs_string") or {}).get("tool.name", "") for s in tools}),
    }
    return checks, summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--model")
    ap.add_argument("--expect-error", action="store_true")
    ap.add_argument("--expect-backend", action="store_true")
    ap.add_argument("--wait", type=int, default=90, help="seconds to wait for the agent-run spans")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    safe = a.project.replace("'", "''")
    deadline = time.time() + a.wait
    spans = []
    while True:
        ids = [r for r in pg(f"select id from tracer_project where name='{safe}' and not deleted").split() if r]
        if ids:
            id_list = ",".join(f"'{i}'" for i in ids)
            spans = ch_rows(f"SELECT {COLUMNS} FROM spans FINAL WHERE project_id IN ({id_list}) AND is_deleted = 0")
        checks, summary = evaluate(spans, a.model, a.expect_error, a.expect_backend)
        if all(checks.values()) or time.time() > deadline:
            break
        time.sleep(5)
    if not spans:
        print(f"no spans stored for project {a.project!r}")
        return 2
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(json.dumps(summary))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"project": a.project, "checks": checks, "summary": summary}, f, indent=1)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
