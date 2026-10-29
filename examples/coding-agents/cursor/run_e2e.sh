#!/usr/bin/env bash
# Drive the real emitter with Cursor hook payloads into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   FI_PROJECT_NAME=cursor-e2e ./run_e2e.sh [fixture.jsonl] [replay.py args...]
#
# Default input is the documented-shape session in
# ../hook-to-otlp/tests/fixtures/cursor/session.jsonl. Each line runs
# emit.py as its own process, exactly as Cursor runs a hook command. Every
# run replaces the fixture's conversation_id and generation_id with fresh
# UUIDs (Cursor's own id shape, so suffixed generation ids such as
# "<id>-0-ab12" still pair up), printed at the end with the trace id.
# Extra arguments go to replay.py (for example --replace MARKER=my-marker).
# Set FI_HOOK_CAPTURE_CONTENT=1 to exercise the content opt-in.
# REPLAY_SLEEP (default 1s) spaces the hooks out so the fixture's reported
# tool durations fit inside the turn, as they would in a real session.
# HOOK_TRANSPORT=stdin|heredoc installs the hooks into a temporary project
# with install.sh and runs the shipped hooks.json commands through $SHELL -c,
# passing the payload on stdin (IDE agent) or as a trailing heredoc (Cursor's
# headless agent host), instead of calling emit.py directly.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/cursor/session.jsonl}"
shift || true
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-cursor-e2e}"

# The fixture's own ids (first record), and fresh UUIDs to replace them with.
read -r SRC_CONV SRC_GEN CONV GEN < <(python3 -B - "$FIXTURE" <<'PY'
import json, re, sys, uuid
payload = json.loads(open(sys.argv[1], encoding="utf-8").readline())["payload"]
conv = payload.get("conversation_id") or payload.get("session_id")
gen = re.sub(r"-\d+-[a-z0-9]{4}$", "", str(payload.get("generation_id") or "-"))
print(conv, gen, uuid.uuid4(), uuid.uuid4())
PY
)

REPLACE=(--replace "$SRC_CONV=$CONV")
if [ "$SRC_GEN" != "-" ]; then REPLACE+=(--replace "$SRC_GEN=$GEN"); fi
VIA=()
if [ -n "${HOOK_TRANSPORT:-}" ]; then
  PROJECT="$(mktemp -d)"
  trap 'rm -rf "$PROJECT"' EXIT
  "$HERE/install.sh" "$PROJECT" >/dev/null
  VIA=(--hooks-json "$PROJECT/.cursor/hooks.json" --cwd "$PROJECT" --transport "$HOOK_TRANSPORT")
  echo "via installed hooks.json, transport=$HOOK_TRANSPORT"
fi
python3 -B "$EMITTER/replay.py" cursor "$FIXTURE" "${REPLACE[@]}" ${VIA[@]+"${VIA[@]}"} \
  --sleep "${REPLAY_SLEEP:-1}" ${@+"$@"}

TRACE_ID="$(cd "$EMITTER" && python3 -B -c 'import sys, emit; print(emit.trace_id("cursor", sys.argv[1]))' "$CONV")"
echo "conversation_id=$CONV"
echo "trace_id=$TRACE_ID"
