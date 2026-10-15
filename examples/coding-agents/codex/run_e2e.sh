#!/usr/bin/env bash
# Real end-to-end check: bridge.py plus one `codex exec` turn that uses a tool,
# exported to Future AGI.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=codex-e2e ./run_e2e.sh
#
# Needs codex (CODEX_BIN or PATH) signed in or configured with a model
# provider. The [otel] settings are passed with `codex exec -c`, so your
# ~/.codex/config.toml is not changed. For a self-hosted Future AGI set
# FI_OTLP_ENDPOINT (e.g. http://localhost:4318/v1/traces).
# CONTENT=1 also exports the prompt (Codex log_user_prompt) and keeps tool
# arguments and output in the bridge (FI_BRIDGE_CAPTURE_CONTENT=1).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
CODEX="${CODEX_BIN:-$(command -v codex || true)}"
[ -x "$CODEX" ] || { echo "codex not found (set CODEX_BIN)" >&2; exit 2; }
PORT="${FI_BRIDGE_PORT:-4319}"
export FI_BRIDGE_LISTEN="127.0.0.1:$PORT" FI_BRIDGE_IDLE_SECONDS="${FI_BRIDGE_IDLE_SECONDS:-5}"
LOG_PROMPT=false
if [ "${CONTENT:-0}" = "1" ]; then
  export FI_BRIDGE_CAPTURE_CONTENT=1
  LOG_PROMPT=true
fi

WORK="$(mktemp -d)"
python3 "$HERE/bridge.py" 2>"$WORK/bridge.log" &
BRIDGE=$!
trap 'kill "$BRIDGE" 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  grep -q "listening" "$WORK/bridge.log" && break
  kill -0 "$BRIDGE" 2>/dev/null || { cat "$WORK/bridge.log" >&2; exit 1; }
  sleep 0.1
done

mkdir -p "$WORK/project"
printf '# demo-project\nA throwaway folder used to test Codex session tracing.\n' >"$WORK/project/README.md"
(cd "$WORK/project" && "$CODEX" exec --skip-git-repo-check \
  -c "otel.exporter={otlp-http={endpoint=\"http://127.0.0.1:$PORT/v1/logs\",protocol=\"json\"}}" \
  -c 'otel.trace_exporter="none"' \
  -c "otel.log_user_prompt=$LOG_PROMPT" \
  "List the files in this folder and read README.md, then tell me its first line." </dev/null) \
  >"$WORK/codex.out" 2>&1

sleep "$((FI_BRIDGE_IDLE_SECONDS + 3))"
kill "$BRIDGE"; wait "$BRIDGE" 2>/dev/null || true
echo "codex_version=$("$CODEX" --version)"
grep -m1 "session id" "$WORK/codex.out" || true
cat "$WORK/bridge.log"
grep -q "http=200" "$WORK/bridge.log" || { echo "nothing exported (see $WORK/codex.out)" >&2; exit 1; }
