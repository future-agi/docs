#!/usr/bin/env bash
# TH-8267 local spike. NOT a supported setup and NOT a relay: nothing here listens for Anthropic.
# STANDIN only: no Anthropic account, API key, model call or spend.
#   A) a synthetic payload shaped like Anthropic's documented Managed Agents API spans, delivered the way
#      the Claude API's delivery rules describe (gzip first, uncompressed resend on 400/415), once as is
#      (expected: rejected, no project_name) and with project_name added (accepted), plus content and failure runs
#   B) the real anthropic Python SDK with its built-in tracing against a local Sessions API stub; the
#      application's own OTLP exporter sends the spans to Future AGI (default, content mode, failure)
# Everything lives under $WORK (default: a fresh temp dir). Secrets are read from the environment, never printed.
#
# needs: python >= 3.10, a local Future AGI collector
# env  : FI_API_KEY FI_SECRET_KEY FI_BASE_URL (collector, e.g. http://localhost:14338)
#        FI_PROJECT_NAME (default th8103-rest-claude-managed-agents)  STUB_PORT (default 18267)
set -euo pipefail
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-th8103-rest-claude-managed-agents}"
STUB_PORT="${STUB_PORT:-18267}"
WORK="${WORK:-$(mktemp -d)}"
PY="${PYTHON:-python3}"

if [ ! -x "$WORK/venv/bin/python" ]; then
  "$PY" -m venv "$WORK/venv"
  "$WORK/venv/bin/pip" install -q -r "$HERE/requirements.txt"
fi
VPY="$WORK/venv/bin/python"

# A) API-span payload
export MARKER="MA$(date +%s)$$A"; echo "api payload    marker=$MARKER"
FI_OTLP_TRACES_URL="${FI_BASE_URL%/}/v1/traces" "$VPY" -I "$HERE/spike/run_fixture_spike.py" "$WORK/fixture_runs.json"

# B) SDK spans against the stub
"$VPY" -I "$HERE/spike/sessions_stub.py" "$STUB_PORT" > "$WORK/stub.log" 2>&1 &
STUB_PID=$!
trap 'kill "$STUB_PID" 2>/dev/null || true' EXIT
sleep 1
export ANTHROPIC_BASE_URL="http://127.0.0.1:$STUB_PORT" ANTHROPIC_API_KEY="stub-not-a-key"
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE ANTHROPIC_OPEN_TELEMETRY
export MARKER="MA$(date +%s)$$OFF"; echo "sdk default    marker=$MARKER"; "$VPY" -I "$HERE/spike/sdk_app.py" ok
export MARKER="MA$(date +%s)$$ON";  echo "sdk content on marker=$MARKER"
ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content "$VPY" -I "$HERE/spike/sdk_app.py" ok
"$VPY" -I "$HERE/spike/sdk_app.py" fail

echo "work=$WORK project=$FI_PROJECT_NAME"
echo "next: check the project in Future AGI (span tree, ERROR spans), then scan every stored column for the printed markers"
