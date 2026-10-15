#!/usr/bin/env bash
# One real Gemini CLI session, exported through otel-collector.yaml to Future AGI.
#
#   FI_API_KEY=... FI_SECRET_KEY=... GEMINI_API_KEY=... ./run_e2e.sh
#
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME
# (default gemini-cli), GEMINI_MODEL (default gemini-3.8-flash),
# GEMINI_OTLP_PORT (port the collector listens on, default 24318),
# GEMINI_BIN / OTELCOL_BIN (default: gemini / otelcol-contrib on PATH),
# CAPTURE_CONTENT=1 to run the documented content opt-in instead.
#
# Gemini CLI runs with a throwaway HOME and project directory, so your own
# ~/.gemini settings and sessions are not read or changed. The prompt asks for
# a directory listing and a file read, so the session has tool calls. The
# collector also writes what it forwards to a local file, which the script
# checks: by default the marker string from the prompt, your user name, home
# directory and machine name must not be in it; with CAPTURE_CONTENT=1 the
# marker must be. The script exits non-zero if a check fails and then keeps its
# work directory for inspection; on success it deletes it.
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
fail() {
  echo "FAIL: $*" >&2
  echo "work directory kept: $WORK" >&2
  exit 1
}
COLLECTOR_ARGS=(--config "$HERE/otel-collector.yaml"
  --set "exporters.file/e2e.path=$WORK/forwarded.json"
  --set "service.pipelines.traces.exporters=[otlphttp/futureagi,file/e2e]")
LOG_PROMPTS=false
if [ "${CAPTURE_CONTENT:-0}" = "1" ]; then
  LOG_PROMPTS=true
  COLLECTOR_ARGS+=(--set "service.pipelines.traces.processors=[transform/gemini-cli,batch]")
fi

"$OTELCOL_BIN" "${COLLECTOR_ARGS[@]}" > "$WORK/collector.log" 2>&1 &
COLLECTOR_PID=$!
trap 'kill "$COLLECTOR_PID" 2>/dev/null || true' EXIT
listening=0
for _ in $(seq 1 50); do
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then listening=1; break; fi
  kill -0 "$COLLECTOR_PID" 2>/dev/null || break
  sleep 0.2
done
if [ "$listening" != 1 ]; then
  tail -5 "$WORK/collector.log" >&2
  fail "the collector is not listening on 127.0.0.1:$PORT (see $WORK/collector.log)"
fi

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
    -p "List the files in this folder and read README.md. Reply with its first heading. $MARKER" \
    < /dev/null
) || echo "gemini exited non-zero; checking what was exported anyway" >&2

# Gemini CLI flushes on exit; give the collector's batch processor time to send.
sleep 5
kill "$COLLECTOR_PID"
wait "$COLLECTOR_PID" 2>/dev/null || true
trap - EXIT
if grep -q -E $'\terror\t|Exporting failed' "$WORK/collector.log"; then
  echo "collector log has errors:" >&2
  grep -E $'\terror\t|Exporting failed' "$WORK/collector.log" | tail -5 >&2
fi

echo "session_id=$SESSION_ID"
echo "marker=$MARKER"
echo "project=$FI_PROJECT_NAME"
touch "$WORK/forwarded.json"
python3 - "$WORK/forwarded.json" <<'EOF'
import json, sys
spans = [s for line in open(sys.argv[1]) if line.strip()
         for rs in json.loads(line)["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]
print("spans_forwarded=%d" % len(spans))
print("span_names=%s" % ",".join(sorted({s["name"] for s in spans})))
EOF
if [ "$LOG_PROMPTS" = true ]; then
  grep -q -F "$MARKER" "$WORK/forwarded.json" || fail "content opt-in: the marker was not forwarded"
  echo "privacy: content opt-in, marker forwarded"
else
  if grep -q -F "$MARKER" "$WORK/forwarded.json"; then fail "the prompt marker was forwarded"; fi
  for needle in "$HOME" "/$(id -un)/" "$(hostname)" "$(hostname -s)"; do
    if grep -q -F "$needle" "$WORK/forwarded.json"; then
      fail "forwarded spans contain a local identity string"
    fi
  done
  echo "privacy: marker, home directory, user name and machine name not forwarded"
fi
rm -rf "$WORK"
