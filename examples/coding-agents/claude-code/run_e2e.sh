#!/usr/bin/env bash
# Real end-to-end check: collector.yaml in otelcol-contrib, then one
# non-interactive Claude Code session that uses tools, exported to Future AGI.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=claude-code-e2e ./run_e2e.sh
#
# Needs otelcol-contrib (OTELCOL_BIN or PATH), claude (CLAUDE_BIN or PATH) and
# a working Claude Code login or ANTHROPIC_API_KEY. For a self-hosted Future
# AGI set FI_OTLP_ENDPOINT (e.g. http://localhost:4318/v1/traces).
# CONTENT=1 also sets the OTEL_LOG_* content flags (prompt, tool input/output).
# The Claude Code variables are passed on the command line only; a
# ~/.claude/settings.json "env" block with OTEL_* keys takes precedence over them.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
OTELCOL="${OTELCOL_BIN:-$(command -v otelcol-contrib || true)}"
CLAUDE="${CLAUDE_BIN:-$(command -v claude || true)}"
[ -x "$OTELCOL" ] || { echo "otelcol-contrib not found (set OTELCOL_BIN)" >&2; exit 2; }
[ -x "$CLAUDE" ] || { echo "claude not found (set CLAUDE_BIN)" >&2; exit 2; }
PORT="${FI_COLLECTOR_PORT:-4318}"
export FI_COLLECTOR_LISTEN="127.0.0.1:$PORT"

WORK="$(mktemp -d)"
LOG="$WORK/otelcol.log"
"$OTELCOL" --config "$HERE/collector.yaml" >"$LOG" 2>&1 &
COLLECTOR=$!
trap 'kill "$COLLECTOR" 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  grep -q "Everything is ready" "$LOG" && break
  kill -0 "$COLLECTOR" 2>/dev/null || { cat "$LOG" >&2; exit 1; }
  sleep 0.2
done

mkdir -p "$WORK/project"
printf '# demo-project\nA throwaway folder used to test Claude Code session tracing.\n' >"$WORK/project/README.md"
CONTENT_FLAGS=()
if [ "${CONTENT:-0}" = "1" ]; then
  CONTENT_FLAGS=(OTEL_LOG_USER_PROMPTS=1 OTEL_LOG_TOOL_DETAILS=1 OTEL_LOG_TOOL_CONTENT=1)
fi

(cd "$WORK/project" && env \
  CLAUDE_CODE_ENABLE_TELEMETRY=1 \
  CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 \
  OTEL_TRACES_EXPORTER=otlp \
  OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
  OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:$PORT" \
  ${CONTENT_FLAGS[@]+"${CONTENT_FLAGS[@]}"} \
  "$CLAUDE" -p "List the files in this folder and read README.md, then tell me its first line." \
    --allowedTools "Read,Glob,Bash(ls:*)" --output-format json </dev/null) >"$WORK/result.json"

sleep 4  # collector batch timeout is 2s
SESSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["session_id"])' "$WORK/result.json")"
echo "claude_version=$("$CLAUDE" --version | head -1)"
echo "session_id=$SESSION_ID"
if grep -q "Exporting failed" "$LOG"; then
  grep "Exporting failed" "$LOG" >&2
  exit 1
fi
echo "exported: open Observe > ${FI_PROJECT_NAME:-claude-code} and filter on session.id=$SESSION_ID"
