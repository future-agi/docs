#!/usr/bin/env bash
# End-to-end run of the OpenRouter Agent recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 \
#   OPENROUTER_API_KEY=sk-or-... MODEL=openai/gpt-4o-mini ./run_e2e.sh
#
# What it does
#   1. npm ci, then the unit tests (recorded responses and a recording collector; no Future AGI needed)
#   2. runs app.mjs against the model endpoint, tracing to FI_BASE_URL, one process per scenario:
#        agent, tool-error, model-error     (project $FI_PROJECT_NAME, metadata only)
#      and again with FI_CAPTURE_CONTENT=1  (project $FI_PROJECT_NAME-content)
#
# Which model endpoint
#   OPENROUTER_API_KEY (+ MODEL)             OpenRouter itself (the default base URL)
#   OPENROUTER_BASE_URL                      any server that speaks the OpenRouter Responses API
#   RESPONSES_SHIM_UPSTREAM=http://host:port  start tools/responses-shim.mjs in front of an OpenAI-compatible
#                                            proxy (it fixes one id that plain OpenAI rejects) and use it
# Other knobs: FI_PROJECT_NAME (default openrouter-agent-e2e), MARKER, SKIP_TESTS=1, SCENARIOS="agent tool-error".
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-https://api.futureagi.com}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-openrouter-agent-e2e}"
export MARKER="${MARKER:-MKR-$(date +%s)-$RANDOM}"
SCENARIOS="${SCENARIOS:-agent tool-error model-error}"

npm ci --silent
node -e 'for (const p of ["@openrouter/agent","@openrouter/sdk","@opentelemetry/sdk-trace-base","@opentelemetry/exporter-trace-otlp-http"]) console.log(p, require(`./node_modules/${p}/package.json`).version)'
echo "node $(node -v)"
[ "${SKIP_TESTS:-0}" = "1" ] || npm test --silent

SHIM_PID=""
trap '[ -n "$SHIM_PID" ] && kill "$SHIM_PID" 2>/dev/null || true' EXIT
if [ -n "${RESPONSES_SHIM_UPSTREAM:-}" ]; then
  node tools/responses-shim.mjs 18266 "$RESPONSES_SHIM_UPSTREAM" &
  SHIM_PID=$!
  sleep 1
  export OPENROUTER_BASE_URL="http://127.0.0.1:18266/v1"
fi
echo "model: ${MODEL:-openai/gpt-4o-mini} at ${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}   marker: $MARKER"

fail=0
run() {
  local out want
  out="$(node app.mjs "$1" 2>/dev/null | grep '^RESULT' || true)"
  echo "${out:-RESULT missing for $1}"
  if [ "$1" = "model-error" ]; then want='"ok":false'; else want='"ok":true'; fi
  echo "$out" | grep -q "$want" || fail=1
}
echo "== metadata only (default): project=$FI_PROJECT_NAME  traces -> $FI_BASE_URL"
for s in $SCENARIOS; do run "$s"; done
echo "== content opt-in (FI_CAPTURE_CONTENT=1): project=$FI_PROJECT_NAME-content"
export FI_CAPTURE_CONTENT=1 FI_PROJECT_NAME="$FI_PROJECT_NAME-content"
for s in $SCENARIOS; do run "$s"; done
exit $fail
