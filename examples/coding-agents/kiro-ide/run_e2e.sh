#!/usr/bin/env bash
# Drive the real emitter with Kiro IDE hook payloads into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   FI_PROJECT_NAME=kiro-ide-e2e ./run_e2e.sh [fixture.jsonl]
#
# Default input is the session in ../hook-to-otlp/tests/fixtures/kiro_ide/session.jsonl,
# shaped like the payloads Kiro IDE 1.2.37 builds. Each line runs emit.py as its
# own process, exactly as Kiro runs a command hook. Every run gets a fresh
# session id, printed at the end with its trace id. Set FI_HOOK_CAPTURE_CONTENT=1
# to exercise the content opt-in.
# HOOK_TRANSPORT=stdin|heredoc installs the recipe into a temporary project with
# install.sh and runs the shipped hook-file commands through $SHELL -c with the
# payload on stdin (what Kiro IDE does) or as a trailing heredoc, instead of
# calling emit.py directly.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EMITTER="$HERE/../hook-to-otlp"
FIXTURE="${1:-$EMITTER/tests/fixtures/kiro_ide/session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-kiro-ide-e2e}"

RUN_ID="kiro-ide-e2e-$(date +%Y%m%d%H%M%S)-$$"
VIA=()
if [ -n "${HOOK_TRANSPORT:-}" ]; then
  PROJECT="$(mktemp -d)"
  trap 'rm -rf "$PROJECT"' EXIT
  "$HERE/install.sh" "$PROJECT" >/dev/null
  # replay.py reads {"hooks": {"<event>": [{"command": ...}]}}; Kiro lists hooks by trigger.
  python3 -B - "$PROJECT/.kiro/hooks/fi-hook-to-otlp.json" "$PROJECT/replay-hooks.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
hooks = {}
for hook in doc["hooks"]:
    hooks.setdefault(hook["trigger"], []).append({"command": hook["action"]["command"]})
json.dump({"hooks": hooks}, open(sys.argv[2], "w", encoding="utf-8"))
PY
  VIA=(--hooks-json "$PROJECT/replay-hooks.json" --cwd "$PROJECT" --transport "$HOOK_TRANSPORT")
  echo "via installed .kiro/hooks/fi-hook-to-otlp.json, transport=$HOOK_TRANSPORT"
fi
python3 -B "$EMITTER/replay.py" kiro_ide "$FIXTURE" \
  --replace "fixture-kiro-ide-session-0001=$RUN_ID" ${VIA[@]+"${VIA[@]}"} \
  --sleep "${REPLAY_SLEEP:-0.3}"

TRACE_ID="$(cd "$EMITTER" && python3 -B -c 'import sys, emit; print(emit.trace_id("kiro_ide", sys.argv[1]))' "$RUN_ID")"
echo "session_id=$RUN_ID"
echo "trace_id=$TRACE_ID"
