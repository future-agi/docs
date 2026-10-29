"""Spike A (STANDIN): replay a synthetic Managed Agents API-span payload into
local Future AGI the way the Claude API's delivery service would send it.

Runs, all into one project:
  reject     metadata_only, delivered exactly as Claude Platform would (no project_name) -> expect rejected
  meta       metadata_only, project_name added in front (what a resource processor does) -> accepted
  content    content mode (opt-in), marker in prompts/tool args/results -> accepted
  failure    metadata_only, a turn whose model request failed (rate_limit_error) -> ERROR spans

Writes evidence/fixture_runs.json (trace ids, delivery attempts). Header values never printed.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deliver import deliver_like_claude_platform  # noqa: E402
from fixture import add_project_name, build  # noqa: E402

URL = os.environ.get("FI_OTLP_TRACES_URL", "http://localhost:14338/v1/traces")
PROJECT = os.environ.get("FI_PROJECT_NAME", "th8103-rest-claude-managed-agents")
MARKER = os.environ["MARKER"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "fixture_runs.json"

headers = {"X-Api-Key": os.environ["FI_API_KEY"], "X-Secret-Key": os.environ["FI_SECRET_KEY"]}
runs = []
for label, mode, failure, stamp in [
    ("reject", "metadata_only", False, False),
    ("meta", "metadata_only", False, True),
    ("content", "content", False, True),
    ("failure", "metadata_only", True, True),
]:
    req, meta = build(mode, MARKER, failure=failure)
    if stamp:
        req = add_project_name(req, PROJECT)
    result = deliver_like_claude_platform(URL, req.SerializeToString(), headers)
    runs.append({"label": label, **meta, "project_name_added": stamp, **result})
    print(f"{label:8s} trace={meta['trace_id']} spans={meta['spans']} mode={mode} "
          f"attempts={[(a['compression'], a['status']) for a in result['attempts']]} delivered={result['delivered']}")
    time.sleep(1)

with open(OUT, "w") as f:
    json.dump({"project": PROJECT, "url": URL, "runs": runs}, f, indent=1)
