#!/usr/bin/env bash
# One real Gemini CLI session, exported through otel-collector.yaml to Future AGI.
#
#   FI_API_KEY=... FI_SECRET_KEY=... GEMINI_API_KEY=... ./run_e2e.sh
#
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME
# (default gemini-cli), GEMINI_MODEL (default gemini-3.8-flash),
# GEMINI_BIN / OTELCOL_BIN (default: gemini / otelcol-contrib on PATH),
# CAPTURE_CONTENT=1 to run the documented content opt-in instead.
#
# Gemini CLI runs with a throwaway HOME and project directory, so your own
# ~/.gemini settings and sessions are not read or changed. The prompt asks for
# a directory listing and a file read, so the session has tool calls. The run
# prints the session id (gen_ai.conversation.id) and a marker string that is
# only in the prompt: with the default config it must not appear in Future AGI.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${GEMINI_API_KEY:?set GEMINI_API_KEY}"
GEMINI_BIN="${GEMINI_BIN:-gemini}"
OTELCOL_BIN="${OTELCOL_BIN:-otelcol-contrib}"
PORT="${GEMINI_OTLP_PORT:-24318}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-gemini-cli}"
export GEMINI_OTLP_LISTEN="127.0.0.1:$PORT"

WORK="$(mktemp -d)"
COLLECTOR_ARGS=(--config "$HERE/otel-collector.yaml")
LOG_PROMPTS=false
if [ "${CAPTURE_CONTENT:-0}" = "1" ]; then
  LOG_PROMPTS=true
  COLLECTOR_ARGS+=(--set "service.pipelines.traces.processors=[transform/gemini-cli,batch]")
fi

"$OTELCOL_BIN" "${COLLECTOR_ARGS[@]}" > "$WORK/collector.log" 2>&1 &
COLLECTOR_PID=$!
trap 'kill "$COLLECTOR_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null && break
  sleep 0.2
done

mkdir -p "$WORK/home/.gemini" "$WORK/project"
python3 - "$HERE/settings.json" "$WORK/home/.gemini/settings.json" "$PORT" "$LOG_PROMPTS" <<'EOF'
import json, sys
src, dst, port, log_prompts = sys.argv[1:]
settings = json.load(open(src))
settings["telemetry"]["otlpEndpoint"] = "http://127.0.0.1:" + port
settings["telemetry"]["logPrompts"] = log_prompts == "true"
settings["security"] = {"auth": {"selectedType": "gemini-api-key"}}
json.dump(settings, open(dst, "w"), indent=2)
EOF
printf '# Gemini CLI E2E fixture\n\nA throwaway project for the Future AGI recipe.\n' > "$WORK/project/README.md"

SESSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
MARKER="FI-E2E-MARKER-$(date +%s)"
(
  cd "$WORK/project"
  HOME="$WORK/home" GEMINI_CLI_TRUST_WORKSPACE=true OTEL_NODE_RESOURCE_DETECTORS=env \
    "$GEMINI_BIN" -m "${GEMINI_MODEL:-gemini-3.8-flash}" --session-id "$SESSION_ID" \
    -p "List the files in this folder and read README.md. Reply with its first heading. $MARKER"
)

# Gemini CLI flushes on exit; give the collector's batch processor time to send.
sleep 5
kill "$COLLECTOR_PID"
wait "$COLLECTOR_PID" 2>/dev/null || true
trap - EXIT
if grep -q -i -E "error|failed" "$WORK/collector.log"; then
  echo "collector log ($WORK/collector.log) has errors:" >&2
  grep -i -E "error|failed" "$WORK/collector.log" | tail -5 >&2
fi
echo "session_id=$SESSION_ID"
echo "marker=$MARKER"
echo "project=$FI_PROJECT_NAME"
