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
# VIA_HOOKS=1 installs the hooks with install.sh into a temporary HOME and
# runs the shipped futureagi.json commands through `sh -c` with the payload
# on stdin, the way grok runs them, instead of calling emit.py directly.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/grok_build/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-grok-build-e2e}"

VIA=()
if [ -n "${VIA_HOOKS:-}" ]; then
  GROK_HOME="$(mktemp -d)"
  trap 'rm -rf "$GROK_HOME"' EXIT
  HOME="$GROK_HOME" "$HERE/install.sh" >/dev/null
  VIA=(--hooks-json "$GROK_HOME/.grok/hooks/futureagi.json" --cwd "$GROK_HOME" --shell /bin/sh)
  echo "via installed futureagi.json (sh -c, payload on stdin)"
fi

RUN_ID="grok-e2e-$(date +%Y%m%d%H%M%S)-$$"
HOME="${GROK_HOME:-$HOME}" python3 -B "$EMITTER/replay.py" grok_build "$FIXTURE" \
  --replace "fixture-grok-session-0001=$RUN_ID" \
  --replace "fixture-grok-session-0002=$RUN_ID-subagent" \
  --replace "fixture-grok-prompt-0001=$RUN_ID-prompt-1" \
  --replace "fixture-grok-prompt-0002=$RUN_ID-prompt-2" \
  ${VIA[@]+"${VIA[@]}"} \
  --sleep "${REPLAY_SLEEP:-0.3}"

for sid in "$RUN_ID" "$RUN_ID-subagent"; do
  TRACE_ID="$(cd "$EMITTER" && python3 -B -c 'import sys, emit; print(emit.trace_id("grok_build", sys.argv[1]))' "$sid")"
  echo "session_id=$sid trace_id=$TRACE_ID"
done
