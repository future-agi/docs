#!/usr/bin/env bash
# Drive the real emitter with Cascade hook payloads into a Future AGI collector,
# running each hook the way Devin Desktop does (the hooks.json command via bash -c).
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   FI_PROJECT_NAME=devin-desktop-e2e ./run_e2e.sh [fixture.jsonl]
#
# Default input is the documented-shape session in
# ../hook-to-otlp/tests/fixtures/devin_desktop/session.jsonl. Every run gets
# a fresh trajectory id, printed at the end with its trace id. Events that
# hooks.json does not register are skipped, as Devin Desktop would.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/devin_desktop/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-devin-desktop-e2e}"

RUN_ID="devin-desktop-e2e-$(date +%Y%m%d%H%M%S)-$$"
python3 - "$FIXTURE" "$RUN_ID" "$HERE/hooks.json" <<'PY' | while IFS=$'\t' read -r event payload; do
import json, sys
registered = json.load(open(sys.argv[3]))["hooks"]
for line in open(sys.argv[1], encoding="utf-8"):
    if not line.strip():
        continue
    record = json.loads(line)
    if record["event"] not in registered:
        continue
    payload = record["payload"]
    payload["trajectory_id"] = sys.argv[2]
    payload["execution_id"] = sys.argv[2] + "-" + payload["execution_id"].rsplit("-", 1)[-1]
    print(record["event"] + "\t" + json.dumps(payload))
PY
  command="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["hooks"][sys.argv[2]][0]["command"])' "$HERE/hooks.json" "$event")"
  command="${command//\$HOME\/.codeium\/windsurf\/fi-hook-to-otlp/$EMITTER}"
  rc=0
  printf '%s' "$payload" | bash -c "$command" >/dev/null || rc=$?
  echo "$event exit=$rc"
  sleep "${REPLAY_SLEEP:-0.3}"
done

TRACE_ID="$(cd "$EMITTER" && python3 -c 'import sys, emit; print(emit.trace_id("devin_desktop", sys.argv[1]))' "$RUN_ID")"
echo "trajectory_id=$RUN_ID"
echo "trace_id=$TRACE_ID"
