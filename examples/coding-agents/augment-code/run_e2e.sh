#!/usr/bin/env bash
# Drive the real emitter, through the same futureagi-hook.sh wrapper Auggie
# runs, with Auggie hook payloads into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   FI_PROJECT_NAME=augment-e2e ./run_e2e.sh [fixture.jsonl]
#
# Default input is the documented-shape session in
# ../hook-to-otlp/tests/fixtures/augment/session.jsonl (it also turns on every
# opt-in metadata block, to show they are dropped). Each line runs the wrapper
# as its own process, exactly as Auggie runs a hook command. Every run gets a
# fresh conversation id, printed at the end with its trace id.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/augment/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-augment-e2e}"

RUN_ID="augment-e2e-$(date +%Y%m%d%H%M%S)-$$"
python3 - "$FIXTURE" "$RUN_ID" <<'PY' | while IFS= read -r payload; do
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    if line.strip():
        payload = json.loads(line)["payload"]
        payload["conversation_id"] = sys.argv[2]
        print(json.dumps(payload))
PY
  rc=0
  printf '%s' "$payload" | "$HERE/futureagi-hook.sh" || rc=$?
  event="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin)["hook_event_name"])')"
  echo "$event exit=$rc"
  sleep "${REPLAY_SLEEP:-0.3}"
done

TRACE_ID="$(cd "$EMITTER" && python3 -B -c 'import sys, emit; print(emit.trace_id("augment", sys.argv[1]))' "$RUN_ID")"
echo "conversation_id=$RUN_ID"
echo "trace_id=$TRACE_ID"
