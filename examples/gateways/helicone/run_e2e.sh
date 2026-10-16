#!/usr/bin/env bash
# End-to-end run: the real, self-hosted Helicone AI Gateway in front of an OpenAI-compatible upstream
# you choose, called by the Python and TypeScript recipes and traced into a Future AGI project.
#
#   E2E_UPSTREAM_URL    origin of the upstream, no /v1 (for example http://127.0.0.1:8317)
#   E2E_UPSTREAM_KEY    key for that upstream (sent by the gateway; never printed)
#   E2E_UPSTREAM_MODEL  a model the upstream serves
#   FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI (a local or self-hosted deployment is fine)
#   FI_PROJECT_NAME     Observe project for the run (default helicone-e2e); "-private", "-ts",
#                       "-proxy-standin" and "-gateway-otlp" projects are created next to it
#   PYTHON              interpreter with requirements.txt installed (default python3)
#   GATEWAY_VERSION     @helicone/ai-gateway version (default 0.2.0-beta.30)
#   GATEWAY_PORT        local port for the gateway (default 18303)
#   FI_GRPC_ENDPOINT    optional, step 7 only: Future AGI OTLP/gRPC endpoint (for example
#                       http://localhost:14337). Sends the gateway's own OpenTelemetry export there.
#   E2E_STEPS           steps to run, default "1 2 3 4 5 6 7" (steps 3 to 7 need step 2)
#
# It starts the gateway on 127.0.0.1 only and removes it on exit. The hosted Helicone endpoints are not called.
set -euo pipefail
set +x
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${E2E_UPSTREAM_URL:?set E2E_UPSTREAM_URL}"
: "${E2E_UPSTREAM_KEY:?set E2E_UPSTREAM_KEY}"
: "${E2E_UPSTREAM_MODEL:?set E2E_UPSTREAM_MODEL}"
: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
PYTHON="${PYTHON:-python3}"
GATEWAY_VERSION="${GATEWAY_VERSION:-0.2.0-beta.30}"
GATEWAY_PORT="${GATEWAY_PORT:-18303}"
FI_PROJECT_NAME="${FI_PROJECT_NAME:-helicone-e2e}"
WORK="${E2E_WORKDIR:-$(mktemp -d)}"
STEPS=" ${E2E_STEPS:-1 2 3 4 5 6 7} "
want() { [[ "$STEPS" == *" $1 "* ]]; }
RAND="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
MARKER="HELI-MARK-$RAND"        # goes into prompts, tool arguments and results
ERR_MARKER="HELI-ERR-$RAND"    # goes into the model name of the failing call, so the gateway echoes it in its error text
GW_PID=""
MOCK_PID=""
cleanup() {
  [ -n "$GW_PID" ] && kill "$GW_PID" 2>/dev/null || true
  [ -n "$MOCK_PID" ] && kill "$MOCK_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait_for_gateway() {
  for _ in $(seq 1 40); do
    curl -s -o /dev/null "http://127.0.0.1:$GATEWAY_PORT/health" && return 0
    kill -0 "$GW_PID" 2>/dev/null || { echo "gateway exited; see $WORK/*.log"; exit 2; }
    sleep 0.5
  done
}

if want 1; then
  echo "== 1. conformance tests against the local stand-in (no network, no keys)"
  (cd "$HERE" && "$PYTHON" -m pytest tests -q)
fi

if want 2; then
  echo "== 2. install the Helicone AI Gateway $GATEWAY_VERSION into $WORK/gw and start it on 127.0.0.1:$GATEWAY_PORT"
  mkdir -p "$WORK/gw"
  (cd "$WORK/gw" && npm init -y >/dev/null 2>&1 && npm install --no-audit --no-fund "@helicone/ai-gateway@$GATEWAY_VERSION" >/dev/null 2>&1 || true)
  # some npm setups block install scripts; the package downloads its binary in postinstall
  (cd "$WORK/gw/node_modules/@helicone/ai-gateway" && node ./install.js >/dev/null 2>&1 || true)
  GW_BIN="$(find "$WORK/gw/node_modules/@helicone/ai-gateway" -type f -name ai-gateway -perm -u+x | head -1)"
  [ -n "$GW_BIN" ] || { echo "gateway binary not found (see $WORK/gw)"; exit 2; }
  echo "$GW_BIN" > "$WORK/gw-bin.path"
  cat > "$WORK/gateway.yaml" <<YAML
server:
  address: "127.0.0.1"
  port: $GATEWAY_PORT
providers:
  openai:
    base-url: "$E2E_UPSTREAM_URL"
    models:
      - $E2E_UPSTREAM_MODEL
YAML
  OPENAI_API_KEY="$E2E_UPSTREAM_KEY" "$GW_BIN" -c "$WORK/gateway.yaml" >"$WORK/gateway.log" 2>&1 &
  GW_PID=$!
  wait_for_gateway
fi

export HELICONE_SURFACE=gateway
export HELICONE_BASE_URL="http://127.0.0.1:$GATEWAY_PORT/ai"
export HELICONE_API_KEY=placeholder-api-key   # the self-hosted gateway has auth off; any value is accepted
export HELICONE_MODEL="openai/$E2E_UPSTREAM_MODEL"
export DEMO_MARKER="$MARKER"

if want 3; then
  echo "== 3. Python recipe, default capture -> project $FI_PROJECT_NAME"
  "$PYTHON" "$HERE/python/run_demo.py" --project "$FI_PROJECT_NAME" --marker "$MARKER" \
    --scenario core --error-model "openai/not-a-model-$ERR_MARKER" 2>&1 | tail -3
fi

if want 4; then
  echo "== 4. Python recipe, content hidden + error details scrubbed -> project $FI_PROJECT_NAME-private"
  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_LLM_INVOCATION_PARAMETERS=true "$PYTHON" "$HERE/python/run_demo.py" \
    --project "$FI_PROJECT_NAME-private" --marker "$MARKER" --scrub-errors \
    --scenario core --error-model "openai/not-a-model-$ERR_MARKER" 2>&1 | tail -3
fi

if want 5; then
  echo "== 5. TypeScript recipe -> project $FI_PROJECT_NAME-ts"
  if [ -d "$HERE/typescript/node_modules/@traceai/openai" ]; then
    (cd "$HERE/typescript" && FI_PROJECT_NAME="$FI_PROJECT_NAME-ts" DEMO_ERROR_MODEL="openai/not-a-model-$ERR_MARKER" node run-demo.ts | tail -1)
  else
    echo "skipped: run 'npm install' in typescript/ first"
  fi
fi

if want 6; then
  echo "== 6. STANDIN: the classic-proxy shape (Helicone-Auth) against the local stand-in -> project $FI_PROJECT_NAME-proxy-standin"
  "$PYTHON" "$HERE/support/mock_helicone.py" --port 0 >"$WORK/mock.log" 2>&1 &
  MOCK_PID=$!
  for _ in $(seq 1 20); do grep -q "mock helicone on" "$WORK/mock.log" 2>/dev/null && break; sleep 0.3; done
  MOCK_BASE="$(sed -n 's/.*mock helicone on \(http[^ ]*\).*/\1/p' "$WORK/mock.log" | head -1)"
  HELICONE_SURFACE=proxy HELICONE_BASE_URL="$MOCK_BASE/proxy/v1" HELICONE_API_KEY=sk-helicone-mock-key \
    OPENAI_API_KEY=sk-provider-mock HELICONE_MODEL="openai/$E2E_UPSTREAM_MODEL" \
    "$PYTHON" "$HERE/python/run_demo.py" --project "$FI_PROJECT_NAME-proxy-standin" --marker "$MARKER" --scenario core 2>&1 | tail -1
  kill "$MOCK_PID" 2>/dev/null || true
  MOCK_PID=""
fi

if want 7 && [ -n "${FI_GRPC_ENDPOINT:-}" ]; then
  echo "== 7. the gateway's own OpenTelemetry export (gRPC) -> project $FI_PROJECT_NAME-gateway-otlp (not an LLM trace; see the docs page)"
  GW_BIN="$(cat "$WORK/gw-bin.path")"
  [ -n "$GW_PID" ] && kill "$GW_PID" 2>/dev/null || true
  [ -n "$GW_PID" ] && wait "$GW_PID" 2>/dev/null || true
  cat > "$WORK/gateway-otlp.yaml" <<YAML
server:
  address: "127.0.0.1"
  port: $GATEWAY_PORT
telemetry:
  level: "info"
  exporter: "otlp"
  otlp-endpoint: "$FI_GRPC_ENDPOINT"
providers:
  openai:
    base-url: "$E2E_UPSTREAM_URL"
    models:
      - $E2E_UPSTREAM_MODEL
YAML
  OPENAI_API_KEY="$E2E_UPSTREAM_KEY" \
    OTEL_EXPORTER_OTLP_HEADERS="x-api-key=$FI_API_KEY,x-secret-key=$FI_SECRET_KEY" \
    OTEL_RESOURCE_ATTRIBUTES="project_name=$FI_PROJECT_NAME-gateway-otlp,project_type=observe" \
    OTEL_SERVICE_NAME=helicone-ai-gateway \
    "$GW_BIN" -c "$WORK/gateway-otlp.yaml" >"$WORK/gateway-otlp.log" 2>&1 &
  GW_PID=$!
  wait_for_gateway
  for _ in 1 2; do
    curl -s -o /dev/null -X POST "http://127.0.0.1:$GATEWAY_PORT/ai/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"openai/$E2E_UPSTREAM_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_completion_tokens\":20}"
  done
  sleep 12   # let the batch exporter flush before the gateway stops
fi

echo "markers for the privacy scan: $MARKER (content) and $ERR_MARKER (error text)"
echo "done. Open Observe in Future AGI and select the projects above."
