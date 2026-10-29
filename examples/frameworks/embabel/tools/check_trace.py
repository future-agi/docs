#!/usr/bin/env python3
"""Check what a self-hosted Future AGI (Docker) stored for the Embabel example.

Reads the project's spans from ClickHouse and checks each trace whose root is the agent span:

  root        the trace has exactly one root, "agent WeatherAgent", typed agent
  hierarchy   action report -> llm <model> -> tool-loop -> chat <model> / execute_tool currentWeather
  llm         every "chat <model>" span is typed llm and has the model and token counts
  tool        "execute_tool currentWeather" is typed tool
  errors      with --tool-error: the tool span is ERROR; with --content-off: its status message is empty

  check_trace.py --project my-project [--min-traces 2] [--tool-error 1] [--content-off]

Prints span names, types and counts, never content. Exit 0 when every check passes.
Container names: FI_PG_CONTAINER, FI_CH_CONTAINER (defaults match the th8103-e2e stack).
"""
import argparse
import json
import os
import subprocess
import sys

PG = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def load(project: str) -> list[dict]:
    safe = project.replace("'", "''")
    ids = _run(["docker", "exec", PG, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc",
                f"select id from tracer_project where name='{safe}' and not deleted"]).split()
    if not ids:
        return []
    id_list = ",".join(f"'{i}'" for i in ids)
    out = _run(["docker", "exec", CH, "clickhouse-client", "-q",
                "SELECT trace_id, id, parent_span_id, name, observation_type, status, status_message, model, "
                "prompt_tokens, completion_tokens FROM spans FINAL "
                f"WHERE project_id IN ({id_list}) AND is_deleted = 0 FORMAT JSONEachRow"])
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def check_trace(spans: list[dict], content_off: bool) -> tuple[list[str], bool]:
    """Returns (failures, tool_errored) for one trace."""
    fails = []
    by_id = {s["id"]: s for s in spans}
    roots = [s for s in spans if s["parent_span_id"] not in by_id]
    if len(roots) != 1 or roots[0]["name"] != "agent WeatherAgent" or roots[0]["observation_type"] != "agent":
        fails.append(f"root: {[(r['name'], r['observation_type']) for r in roots]}")

    def parent_name(s: dict) -> str:
        p = by_id.get(s["parent_span_id"])
        return p["name"] if p else ""

    for s in spans:
        name, parent = s["name"], parent_name(s)
        if name == "action report" and parent != "agent WeatherAgent":
            fails.append(f"hierarchy: action under {parent!r}")
        if name.startswith("llm ") and not name.startswith("llm.") and parent != "action report":
            fails.append(f"hierarchy: {name} under {parent!r}")
        if name == "tool-loop" and not parent.startswith("llm "):
            fails.append(f"hierarchy: tool-loop under {parent!r}")
        if name.startswith("chat "):
            if parent != "tool-loop":
                fails.append(f"hierarchy: {name} under {parent!r}")
            if s["observation_type"] != "llm" or not s["model"]:
                fails.append(f"llm: {name} type={s['observation_type']} model={s['model']!r}")
            if s["status"] != "ERROR" and not (int(s["prompt_tokens"] or 0) and int(s["completion_tokens"] or 0)):
                fails.append(f"llm: {name} has no token counts")
        if name == "execute_tool currentWeather":
            if parent != "tool-loop" or s["observation_type"] != "tool":
                fails.append(f"tool: under {parent!r} type={s['observation_type']}")
    tools = [s for s in spans if s["name"] == "execute_tool currentWeather"]
    errored = [t for t in tools if t["status"] == "ERROR"]
    if content_off and any(t["status_message"] for t in errored):
        fails.append("errors: tool status message is not empty with content off")
    return fails, bool(errored)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--min-traces", type=int, default=1)
    ap.add_argument("--tool-error", type=int, default=0, help="number of traces whose tool span must be ERROR")
    ap.add_argument("--content-off", action="store_true")
    a = ap.parse_args()

    traces: dict[str, list[dict]] = {}
    for s in load(a.project):
        traces.setdefault(s["trace_id"], []).append(s)
    agent_traces = {t: ss for t, ss in traces.items() if any(s["name"] == "agent WeatherAgent" for s in ss)}
    bad, tool_errors = False, 0
    for tid, ss in sorted(agent_traces.items()):
        fails, errored = check_trace(ss, a.content_off)
        tool_errors += errored
        kinds = sorted({s["observation_type"] for s in ss})
        print(f"trace {tid}: {len(ss)} spans, types {kinds}, tool error: {errored}: {'PASS' if not fails else 'FAIL ' + '; '.join(fails)}")
        bad |= bool(fails)
    if len(agent_traces) < a.min_traces:
        print(f"FAIL: {len(agent_traces)} agent trace(s), expected at least {a.min_traces}")
        bad = True
    if tool_errors < a.tool_error:
        print(f"FAIL: {tool_errors} trace(s) with an ERROR tool span, expected at least {a.tool_error}")
        bad = True
    print("RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
