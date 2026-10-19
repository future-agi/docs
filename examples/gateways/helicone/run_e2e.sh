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
#   FI_GRPC_ENDPOINT    optional, step 7 only: Future AGI OTLP/gRPC endpoint WITH its scheme (for example
#                       http://localhost:14337). Sends the gateway's own OpenTelemetry export there. Without a
#                       scheme ("localhost:14337") the gateway exports nothing and logs no error, so the script
#                       refuses it. Step 7 is skipped when this is unset.
#   FI_VERIFY           required with FI_GRPC_ENDPOINT: a script, run as
#                       "$PYTHON $FI_VERIFY --project NAME --wait SECONDS --min-spans N", that reads the project
#                       back from Future AGI and exits 0 only when it holds at least N stored spans. Step 7 fails
#                       when it exits non-zero.
#   STEP7_SETTLE        seconds the gateway keeps running after the step 7 requests (default 5)
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

# Step 7 settings are checked before anything is installed or run.
if want 7 && [ -n "${FI_GRPC_ENDPOINT:-}" ]; then
  case "$FI_GRPC_ENDPOINT" in
    http://?*|https://?*) ;;
    *)
      echo "FAIL step 7: FI_GRPC_ENDPOINT must include the scheme, for example http://localhost:14337 (got '$FI_GRPC_ENDPOINT')." >&2
      echo "  With no scheme the gateway starts, serves requests and exports nothing, without logging an error." >&2
      exit 2 ;;
  esac
  if [ -z "${FI_VERIFY:-}" ] || [ ! -f "$FI_VERIFY" ]; then
    echo "FAIL step 7: set FI_VERIFY to a script that reads the project back from Future AGI (see the header of this file)," >&2
    echo "  or unset FI_GRPC_ENDPOINT to skip step 7. Without it the export cannot be shown to have been stored." >&2
    exit 2
  fi
fi

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

echo "markers for the privacy scan: $MARKER (content) and $ERR_MARKER (error text)"

if want 7 && [ -z "${FI_GRPC_ENDPOINT:-}" ]; then
  echo "== 7. skipped: FI_GRPC_ENDPOINT is not set (the gateway's own telemetry was not tested)"
elif want 7; then
  P7="$FI_PROJECT_NAME-gateway-otlp"
  echo "== 7. the gateway's own OpenTelemetry export (gRPC) to $FI_GRPC_ENDPOINT -> project $P7 (not an LLM trace; see the docs page)"
  [ -s "$WORK/gw-bin.path" ] || { echo "FAIL step 7: run step 2 first (it installs the gateway)"; exit 1; }
  GW_BIN="$(cat "$WORK/gw-bin.path")"
  [ -n "$GW_PID" ] && kill "$GW_PID" 2>/dev/null || true
  [ -n "$GW_PID" ] && wait "$GW_PID" 2>/dev/null || true
  GW_PID=""
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
  # Both variables are read by the gateway's OpenTelemetry exporter. OTEL_SERVICE_NAME is not: service.name
  # comes from the gateway's telemetry.service-name setting (default "ai-gateway").
  OPENAI_API_KEY="$E2E_UPSTREAM_KEY" \
    OTEL_EXPORTER_OTLP_HEADERS="x-api-key=$FI_API_KEY,x-secret-key=$FI_SECRET_KEY" \
    OTEL_RESOURCE_ATTRIBUTES="project_name=$P7,project_type=observe" \
    "$GW_BIN" -c "$WORK/gateway-otlp.yaml" >"$WORK/gateway-otlp.log" 2>&1 &
  GW_PID=$!
  wait_for_gateway
  for i in 1 2; do
    code="$(curl -s -o "$WORK/step7-response-$i.json" -w '%{http_code}' -X POST "http://127.0.0.1:$GATEWAY_PORT/ai/chat/completions" \
      -H 'Content-Type: application/json' \
      -d "{\"model\":\"openai/$E2E_UPSTREAM_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_completion_tokens\":20}" || true)"
    [ "$code" = 200 ] || { echo "FAIL step 7: request $i through the gateway returned HTTP $code (see $WORK/step7-response-$i.json)"; exit 1; }
  done
  sleep "${STEP7_SETTLE:-5}"
  # Stop the gateway before the check: its shutdown sends the spans it still holds.
  kill "$GW_PID" 2>/dev/null || true
  wait "$GW_PID" 2>/dev/null || true
  GW_PID=""
  stored=""
  for _ in 1 2 3; do
    if "$PYTHON" "$FI_VERIFY" --project "$P7" --wait 120 --min-spans 2 >"$WORK/step7-verify.txt" 2>&1; then stored=1; break; fi
    grep -qi 'clickhouse error' "$WORK/step7-verify.txt" || break   # retry only when the storage could not be read
    sleep 30
  done
  if [ -z "$stored" ]; then
    echo "FAIL step 7: no spans stored in project $P7 (gateway log: $WORK/gateway-otlp.log)"
    sed -n '1,5p' "$WORK/step7-verify.txt" | cut -c1-200
    exit 1
  fi
  echo "PASS step 7: spans stored in project $P7"
  sed -n '1,2p' "$WORK/step7-verify.txt" | cut -c1-200
fi

echo "done. Open Observe in Future AGI and select the projects above."
