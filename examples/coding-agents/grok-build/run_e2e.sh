#!/usr/bin/env bash
# Drive the real emitter with Grok Build hook payloads into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   FI_PROJECT_NAME=grok-build-e2e ./run_e2e.sh [fixture.jsonl]
#
# Default input is a sanitized capture of a real grok 1.0.52 session with a
# subagent (../hook-to-otlp/tests/fixtures/grok_build/session.jsonl). Each
# line runs emit.py as its own process, exactly as grok runs a hook command.
# Every run gets fresh session ids, printed at the end with the trace ids.
# Set FI_HOOK_CAPTURE_CONTENT=1 to exercise the content opt-in.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/grok_build/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-grok-build-e2e}"

RUN_ID="grok-e2e-$(date +%Y%m%d%H%M%S)-$$"
python3 "$EMITTER/replay.py" grok_build "$FIXTURE" \
  --replace "fixture-grok-session-0001=$RUN_ID" \
  --replace "fixture-grok-session-0002=$RUN_ID-subagent" \
  --replace "fixture-grok-prompt-0001=$RUN_ID-prompt-1" \
  --replace "fixture-grok-prompt-0002=$RUN_ID-prompt-2" \
  --sleep "${REPLAY_SLEEP:-0.3}"

for sid in "$RUN_ID" "$RUN_ID-subagent"; do
  TRACE_ID="$(cd "$EMITTER" && python3 -c 'import sys, emit; print(emit.trace_id("grok_build", sys.argv[1]))' "$sid")"
  echo "session_id=$sid trace_id=$TRACE_ID"
done
