#!/usr/bin/env bash
# Drive the real emitter with Kiro CLI hook payloads into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   FI_PROJECT_NAME=kiro-cli-e2e ./run_e2e.sh [fixture.jsonl]
#
# Default input is the session in ../hook-to-otlp/tests/fixtures/kiro_cli/session.jsonl,
# shaped like the Kiro CLI V3 payloads in the Kiro hook docs. Each line runs emit.py as its
# own process, exactly as Kiro CLI runs a command hook. Every run gets a fresh
# session id, printed at the end with its trace id. Set FI_HOOK_CAPTURE_CONTENT=1
# to exercise the content opt-in.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/kiro_cli/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-kiro-cli-e2e}"

RUN_ID="kiro-cli-e2e-$(date +%Y%m%d%H%M%S)-$$"
python3 "$EMITTER/replay.py" kiro_cli "$FIXTURE" \
  --replace "fixture-kiro-cli-session-0001=$RUN_ID" \
  --sleep "${REPLAY_SLEEP:-0.3}"

TRACE_ID="$(cd "$EMITTER" && python3 -c 'import sys, emit; print(emit.trace_id("kiro_cli", sys.argv[1]))' "$RUN_ID")"
echo "session_id=$RUN_ID"
echo "trace_id=$TRACE_ID"
