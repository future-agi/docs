#!/usr/bin/env bash
# Drive the real bridge with Cowork log exports shaped as Anthropic documents
# them, into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=cowork-e2e ./run_e2e.sh [fixture.jsonl]
#
# The bridge runs on loopback with a bearer token, the way the admin form
# would call it, and each replay gets fresh session and prompt ids.
# For a self-hosted Future AGI set FI_OTLP_ENDPOINT (e.g. http://localhost:4318/v1/traces).
# CONTENT=1 turns on FI_BRIDGE_CAPTURE_CONTENT.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FIXTURE="${1:-$HERE/tests/fixtures/cowork-documented-session.jsonl}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
PORT="${FI_BRIDGE_PORT:-4320}"
export FI_BRIDGE_LISTEN="127.0.0.1:$PORT" FI_BRIDGE_IDLE_SECONDS="${FI_BRIDGE_IDLE_SECONDS:-3}"
export FI_BRIDGE_TOKEN="${FI_BRIDGE_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_hex(16))')}"
[ "${CONTENT:-0}" = "1" ] && export FI_BRIDGE_CAPTURE_CONTENT=1

LOG="$(mktemp)"
python3 "$HERE/bridge.py" 2>"$LOG" &
BRIDGE=$!
trap 'kill "$BRIDGE" 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  grep -q "listening" "$LOG" && break
  kill -0 "$BRIDGE" 2>/dev/null || { cat "$LOG" >&2; exit 1; }
  sleep 0.1
done

python3 "$HERE/replay.py" "$FIXTURE" --url "http://127.0.0.1:$PORT/v1/logs" --token "$FI_BRIDGE_TOKEN" --sleep "${REPLAY_SLEEP:-1}"
sleep "$((FI_BRIDGE_IDLE_SECONDS + 2))"
kill "$BRIDGE"; wait "$BRIDGE" 2>/dev/null || true
cat "$LOG"
grep -q "http=200" "$LOG" || { echo "nothing exported" >&2; exit 1; }
