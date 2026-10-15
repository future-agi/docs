#!/usr/bin/env bash
# One real OpenClaw agent turn, exported by diagnostics-otel to Future AGI.
#
#   FI_API_KEY=... FI_SECRET_KEY=... \
#   MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1 MODEL_API_KEY=... MODEL_ID=... \
#   ./run_e2e.sh
#
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME
# (default openclaw), OPENCLAW_BIN (default openclaw on PATH),
# CAPTURE_CONTENT=1 for the content opt-in, GATEWAY=1 to start a Gateway on
# GATEWAY_PORT (default 28789) and dispatch the turn through it instead of
# `openclaw agent --local`.
#
# OpenClaw runs with OPENCLAW_HOME set to a temporary directory, so your own
# ~/.openclaw config, sessions and Gateway are not read or changed. The prompt
# asks for a directory listing and a file read, so the turn has tool calls. The
# printed marker is only in the prompt: with the default config it must not
# appear in Future AGI.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${MODEL_BASE_URL:?set MODEL_BASE_URL}" "${MODEL_API_KEY:?set MODEL_API_KEY}" "${MODEL_ID:?set MODEL_ID}"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"
FI_BASE_URL="${FI_BASE_URL:-https://api.futureagi.com}"
FI_PROJECT_NAME="${FI_PROJECT_NAME:-openclaw}"
GATEWAY_PORT="${GATEWAY_PORT:-28789}"

WORK="$(mktemp -d)"
export OPENCLAW_HOME="$WORK"
STATE="$WORK/.openclaw"
mkdir -p "$STATE" "$WORK/project"
printf '# OpenClaw E2E fixture\n\nA throwaway project for the Future AGI recipe.\n' > "$WORK/project/README.md"

"$OPENCLAW_BIN" plugins install clawhub:@openclaw/diagnostics-otel

# The documented patch, pointed at FI_BASE_URL and with the content switch applied.
python3 - "$HERE/futureagi.patch.json5" "$WORK/futureagi.patch.json5" "$FI_BASE_URL" "${CAPTURE_CONTENT:-0}" <<'EOF'
import sys
src, dst, base, capture = sys.argv[1:]
text = open(src).read().replace("https://api.futureagi.com", base.rstrip("/"))
if capture == "1":
    text = text.replace("captureContent: false", "captureContent: true")
open(dst, "w").write(text)
EOF
"$OPENCLAW_BIN" config patch --file "$WORK/futureagi.patch.json5"

# A model for the turn: any OpenAI-compatible endpoint.
cat > "$WORK/model.patch.json5" <<EOF
{
  agents: { defaults: { model: { primary: "e2e/$MODEL_ID" } } },
  models: {
    mode: "merge",
    providers: {
      e2e: {
        baseUrl: "$MODEL_BASE_URL",
        apiKey: "\${MODEL_API_KEY}",
        api: "openai-completions",
        models: [{ id: "$MODEL_ID", name: "$MODEL_ID" }],
      },
    },
  },
}
EOF
"$OPENCLAW_BIN" config patch --file "$WORK/model.patch.json5"

GATEWAY_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
umask 077
{
  echo "FI_API_KEY=$FI_API_KEY"
  echo "FI_SECRET_KEY=$FI_SECRET_KEY"
  echo "OTEL_RESOURCE_ATTRIBUTES=project_name=$FI_PROJECT_NAME"
  echo "OTEL_NODE_RESOURCE_DETECTORS=env"
  echo "MODEL_API_KEY=$MODEL_API_KEY"
  echo "OPENCLAW_GATEWAY_TOKEN=$GATEWAY_TOKEN"
} > "$STATE/.env"
umask 022
"$OPENCLAW_BIN" config validate

SESSION_ID="fi-e2e-$(date +%s)"
MARKER="FI-E2E-MARKER-$(date +%s)"
PROMPT="Use your tools to list the files in $WORK/project and read README.md there. Reply with its first heading. $MARKER"
# Run with only the .env file as configuration, as a Gateway service would.
unset FI_API_KEY FI_SECRET_KEY MODEL_API_KEY
cd "$WORK/project"
if [ "${GATEWAY:-0}" = "1" ]; then
  "$OPENCLAW_BIN" config patch --stdin <<EOF
{ gateway: { mode: "local", port: $GATEWAY_PORT, bind: "loopback", auth: { mode: "token", token: "\${OPENCLAW_GATEWAY_TOKEN}" } } }
EOF
  "$OPENCLAW_BIN" gateway --port "$GATEWAY_PORT" > "$WORK/gateway.log" 2>&1 &
  GATEWAY_PID=$!
  trap 'kill "$GATEWAY_PID" 2>/dev/null || true' EXIT
  # The port opens before startup finishes; wait for the ready line.
  for _ in $(seq 1 240); do
    grep -q "http server listening" "$WORK/gateway.log" && break
    sleep 1
  done
  OPENCLAW_GATEWAY_TOKEN="$GATEWAY_TOKEN" "$OPENCLAW_BIN" agent --session-id "$SESSION_ID" -m "$PROMPT"
  sleep 30  # let the run finish and a few batch intervals pass, then stop the Gateway (it flushes on shutdown)
  kill "$GATEWAY_PID"
  wait "$GATEWAY_PID" 2>/dev/null || true
  trap - EXIT
else
  "$OPENCLAW_BIN" agent --local --session-id "$SESSION_ID" -m "$PROMPT"
fi
echo "openclaw_home=$WORK"
echo "marker=$MARKER"
echo "project=$FI_PROJECT_NAME"
