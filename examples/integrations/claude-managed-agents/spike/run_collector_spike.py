"""STANDIN: deliver synthetic Managed Agents API spans to the collector recipe (otelcol.yaml) the way the
Claude API delivery service does (gzip first, uncompressed resend on 400/415, destination headers only).

usage: run_collector_spike.py <receiver-url> <scenario> <out.json>
scenarios (each needs the env var MARKER; the destination token is read from ANTHROPIC_DEST_TOKEN):
  metadata   Metadata-only payload (Anthropic's default)
  content    Full-content payload, markers in prompts, tool arguments and results
  error      a turn whose model request failed (rate_limit_error)
  duplicate  the same metadata payload delivered twice (same trace and span ids), as at-least-once delivery allows
  badtoken   metadata payload with a wrong token (expect rejected)
Nothing is printed except status codes, trace ids and counts.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deliver import deliver_like_claude_platform  # noqa: E402
from fixture import build  # noqa: E402

url, scenario, out = sys.argv[1], sys.argv[2], sys.argv[3]
marker = os.environ["MARKER"]
token = os.environ["ANTHROPIC_DEST_TOKEN"]
headers = {"Authorization": f"Bearer {'wrong-token' if scenario == 'badtoken' else token}"}
mode = "content" if scenario == "content" else "metadata_only"
req, meta = build(mode, marker, failure=(scenario == "error"))
payload = req.SerializeToString()
results = [deliver_like_claude_platform(url, payload, headers)]
if scenario == "duplicate":
    results.append(deliver_like_claude_platform(url, payload, headers))
for r in results:
    print(f"{scenario:9s} trace={meta['trace_id']} spans={meta['spans']} "
          f"attempts={[(a['compression'], a['status']) for a in r['attempts']]} delivered={r['delivered']}")
with open(out, "w") as f:
    json.dump({"scenario": scenario, **meta, "deliveries": results}, f, indent=1)
