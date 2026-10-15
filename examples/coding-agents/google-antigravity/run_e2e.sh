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
# HOOK_TRANSPORT=stdin|heredoc installs the recipe into a temporary project with
# install.sh and runs the shipped .agents/hooks.json commands through $SHELL -c in
# .agents/ (as Antigravity does), with the payload on stdin (what Antigravity does)
# or as a trailing heredoc, instead of calling emit.py directly.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/antigravity/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-antigravity-e2e}"

RUN_ID="ag-e2e-$(date +%Y%m%d%H%M%S)-$$"
VIA=(--pass-event)
if [ -n "${HOOK_TRANSPORT:-}" ]; then
  PROJECT="$(mktemp -d)"
  trap 'rm -rf "$PROJECT"' EXIT
  "$HERE/install.sh" "$PROJECT" >/dev/null
  # replay.py reads {"hooks": {"<event>": [...]}}: wrap the installed "fi-hook-to-otlp" member.
  python3 -B - "$PROJECT/.agents/hooks.json" "$PROJECT/replay-hooks.json" <<'PY'
import json, sys
entry = json.load(open(sys.argv[1], encoding="utf-8"))["fi-hook-to-otlp"]
json.dump({"hooks": entry}, open(sys.argv[2], "w", encoding="utf-8"))
PY
  VIA=(--hooks-json "$PROJECT/replay-hooks.json" --cwd "$PROJECT/.agents" --transport "$HOOK_TRANSPORT")
  echo "via installed .agents/hooks.json, transport=$HOOK_TRANSPORT"
fi
python3 -B "$EMITTER/replay.py" antigravity "$FIXTURE" "${VIA[@]}" \
  --replace "fixture-ag-conv-0001=$RUN_ID" \
  --sleep "${REPLAY_SLEEP:-0.3}"

TRACE_ID="$(cd "$EMITTER" && python3 -B -c 'import sys, emit; print(emit.trace_id("antigravity", sys.argv[1]))' "$RUN_ID")"
echo "conversation_id=$RUN_ID"
echo "trace_id=$TRACE_ID"
