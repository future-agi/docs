#!/usr/bin/env bash
# Drive the real emitter with Antigravity IDE hook payloads into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   FI_PROJECT_NAME=antigravity-e2e ./run_e2e.sh [fixture.jsonl]
#
# Default input is the session in ../hook-to-otlp/tests/fixtures/antigravity/session.jsonl,
# shaped as https://antigravity.google/docs/hooks documents the IDE payloads.
# Each line runs emit.py as its own process with the event name on argv, exactly
# as the hooks.json command does. Every run gets a fresh conversation id, printed
# at the end with its trace id. Set FI_HOOK_CAPTURE_CONTENT=1 to exercise the
# content opt-in.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/antigravity/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-antigravity-e2e}"

RUN_ID="ag-e2e-$(date +%Y%m%d%H%M%S)-$$"
python3 "$EMITTER/replay.py" antigravity "$FIXTURE" --pass-event \
  --replace "fixture-ag-conv-0001=$RUN_ID" \
  --sleep "${REPLAY_SLEEP:-0.3}"

TRACE_ID="$(cd "$EMITTER" && python3 -c 'import sys, emit; print(emit.trace_id("antigravity", sys.argv[1]))' "$RUN_ID")"
echo "conversation_id=$RUN_ID"
echo "trace_id=$TRACE_ID"
