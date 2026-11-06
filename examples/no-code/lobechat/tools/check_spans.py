#!/usr/bin/env python3
"""Check the LobeHub spans stored by a self-hosted Future AGI (reads its ClickHouse container).

Conformance checks for the recipe, run by run_e2e.sh after real LobeHub agent runs:
  - every trace has exactly one root, no span points at a parent that was not stored,
  - only agent runtime spans and the request span that started the run are stored (no HTTP, Next.js
    render, database or socket spans),
  - span types: invoke_agent = agent, chat = llm, execute_tool = tool, the rest = chain,
  - the llm spans carry the model and token counts, agent spans carry no token counts (counted once),
  - tool spans carry the tool name, agent and llm spans carry the session (LobeHub conversation id),
  - with --expect-error: an ERROR llm span and an ERROR agent span,
  - resource attributes hold no host, OS, process or container keys.

  check_spans.py --project lobehub-e2e --model gpt-4o-mini [--expect-error] [--since 2026-10-17T08:00:00Z]
                 [--json out.json]

Exit 0 when every check passes. Prints check names and counts, never span contents.
Container defaults to the TH-8103 local stack; override with FI_CH_CONTAINER / FI_PG_CONTAINER.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

CH_CONTAINER = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")
PG_CONTAINER = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")

AGENT_RUNTIME_PREFIXES = (
    "invoke_agent", "chat ", "execute_tool ", "context_engineering", "execAgent ", "turn_setup ",
    "tool_discovery ", "operation_start ",
)
ENTRY_PREFIXES = ("tRPC MUTATION aiAgent.", "executing api route (app) /api/agent/")
EXPECTED_TYPE = {"invoke_agent": "agent", "chat ": "llm", "execute_tool ": "tool"}
FORBIDDEN_RESOURCE_PREFIXES = ("host.", "os.", "process.", "container.")


def expected_type(name: str) -> str:
    for prefix, kind in EXPECTED_TYPE.items():
        if name.startswith(prefix):
            return kind
    return "chain"


def check(spans: list[dict], model: str, expect_error: bool = False) -> dict[str, tuple[bool, str]]:
    """Pure checks over stored span rows. Returns {check name: (passed, detail)}."""
    res: dict[str, tuple[bool, str]] = {}
    by_trace: dict[str, list[dict]] = defaultdict(list)
    for s in spans:
        by_trace[s["trace_id"]].append(s)
    agent_traces = {t: ss for t, ss in by_trace.items() if any(x["name"].startswith("invoke_agent") for x in ss)}

    res["spans stored"] = (bool(spans), f"{len(spans)} spans, {len(by_trace)} traces")
    res["agent run traces"] = (bool(agent_traces), f"{len(agent_traces)} traces with invoke_agent")

    bad_roots = {t: sum(1 for x in ss if not x["parent_span_id"]) for t, ss in agent_traces.items()}
    bad_roots = {t: n for t, n in bad_roots.items() if n != 1}
    res["one root per agent run trace"] = (not bad_roots, f"traces with != 1 root: {len(bad_roots)}")

    orphans = []
    for ss in agent_traces.values():
        ids = {x["id"] for x in ss}
        orphans += [x["name"] for x in ss if x["parent_span_id"] and x["parent_span_id"] not in ids]
    res["no orphan spans"] = (not orphans, f"{len(orphans)} orphans {sorted(set(orphans))[:5]}")

    foreign = sorted({x["name"] for x in spans
                      if not x["name"].startswith(AGENT_RUNTIME_PREFIXES + ENTRY_PREFIXES)})
    res["only agent runtime + entry spans"] = (not foreign, f"other span names: {foreign[:8]}")

    roots = sorted({x["name"] for ss in agent_traces.values() for x in ss if not x["parent_span_id"]})
    res["root is the request span"] = (all(r.startswith(ENTRY_PREFIXES) for r in roots) and bool(roots),
                                       f"roots: {roots}")

    wrong = sorted({(x["name"], x["observation_type"]) for x in spans
                    if x["observation_type"] != expected_type(x["name"])})
    res["span types"] = (not wrong, f"mismatches: {wrong[:6]}")

    llm = [x for x in spans if x["name"].startswith("chat ") and x["status"] != "ERROR"]
    res["llm model"] = (bool(llm) and all(x["model"] == model for x in llm),
                        f"{len(llm)} ok llm spans, models {sorted({x['model'] for x in llm})}")
    res["llm tokens"] = (bool(llm) and all(x["prompt_tokens"] > 0 and x["completion_tokens"] > 0 for x in llm),
                         f"{sum(1 for x in llm if x['prompt_tokens'] > 0)} of {len(llm)} with tokens")
    agents = [x for x in spans if x["name"].startswith("invoke_agent")]
    res["tokens counted once"] = (all(x["prompt_tokens"] == 0 and x["completion_tokens"] == 0 for x in agents),
                                  f"{sum(1 for x in agents if x['prompt_tokens'])} agent spans with tokens")

    tools = [x for x in spans if x["name"].startswith("execute_tool ")]
    res["tool span with tool name"] = (bool(tools) and all(x["attrs"].get("tool.name") for x in tools),
                                       f"{len(tools)} tool spans {sorted({x['attrs'].get('tool.name') for x in tools})}")

    sess = [x for x in spans if x["name"].startswith(("invoke_agent", "chat "))]
    res["session on agent and llm spans"] = (bool(sess) and all(x["session"] for x in sess),
                                             f"{sum(1 for x in sess if x['session'])} of {len(sess)}")

    if expect_error:
        err_llm = [x for x in spans if x["name"].startswith("chat ") and x["status"] == "ERROR"]
        err_agent = [x for x in agents if x["status"] == "ERROR"]
        res["ERROR llm span"] = (bool(err_llm), f"{len(err_llm)}")
        res["ERROR agent span"] = (bool(err_agent), f"{len(err_agent)}")

    res_keys = sorted({k for x in spans for k in x["resource_keys"]})
    leaked = [k for k in res_keys if k.startswith(FORBIDDEN_RESOURCE_PREFIXES)]
    res["no host/os/process resource keys"] = (not leaked and "project_name" in res_keys,
                                              f"resource keys: {res_keys}")
    return res


def _run(cmd: list[str], tries: int = 4) -> str:
    out = None
    for attempt in range(tries):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(out.stderr.strip()[:200])


def _flatten_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten_keys(v, f"{prefix}{k}.")
    else:
        yield prefix[:-1]


def fetch(project: str, since: str | None = None) -> list[dict]:
    safe = project.replace("'", "''")
    pids = _run(["docker", "exec", PG_CONTAINER, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc",
                 f"select id from tracer_project where name='{safe}' and not deleted"]).split()
    if not pids:
        return []
    ids = ",".join(f"'{p}'" for p in pids)
    sql = ("SELECT trace_id, id, parent_span_id, name, observation_type, status, model, prompt_tokens, "
           "completion_tokens, toString(trace_session_id) AS session, attrs_string AS attrs, "
           "toJSONString(resource_attrs) AS resource "
           f"FROM spans FINAL WHERE project_id IN ({ids}) AND is_deleted=0")
    if since:
        sql += f" AND start_time >= parseDateTime64BestEffort('{since.replace(chr(39), '')}', 6)"
    sql += " FORMAT JSONEachRow"
    rows = []
    for line in _run(["docker", "exec", CH_CONTAINER, "clickhouse-client", "-q", sql]).splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        r["session"] = "" if r.get("session") in (None, "", "\\N") else r["session"]
        try:
            res = json.loads(r.pop("resource") or "{}")
        except ValueError:
            res = {}
        r["resource_keys"] = sorted(set(_flatten_keys(res)))
        rows.append(r)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--expect-error", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--wait", type=int, default=60, help="seconds to wait for agent spans to appear")
    ap.add_argument("--since", help="only spans that started at or after this UTC time (ISO 8601)")
    ap.add_argument("--min-runs", type=int, default=1, help="agent run traces to wait for")
    a = ap.parse_args(argv)
    # Spans arrive in batches (LobeHub ~5 s, collector 2 s, then Future AGI ingestion): wait until the
    # expected agent runs are there and the stored span count has stopped changing.
    deadline = time.time() + a.wait
    spans, last = fetch(a.project, a.since), -1
    while time.time() < deadline:
        runs = {s["trace_id"] for s in spans if s["name"].startswith("invoke_agent")}
        if len(runs) >= a.min_runs and len(spans) == last:
            break
        last = len(spans)
        time.sleep(10)
        spans = fetch(a.project, a.since)
    res = check(spans, a.model, a.expect_error)
    ok = all(p for p, _ in res.values())
    for name, (passed, detail) in res.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")
    print("RESULT:", "PASS" if ok else "FAIL")
    if a.json:
        with open(a.json, "w") as f:
            json.dump({k: {"pass": p, "detail": d} for k, (p, d) in res.items()}, f, indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
