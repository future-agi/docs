#!/usr/bin/env bash
# End-to-end test of the Cloudflare Think recipe against a running Future AGI (self-hosted or cloud).
#
#   real   Think (@cloudflare/think) in the real Workers runtime: `wrangler dev` (workerd, local mode,
#          no Cloudflare account), a real model behind an OpenAI-compatible endpoint, one tool.
#   real   otelcol.yaml in otel/opentelemetry-collector-contrib (Docker), forwarding to Future AGI.
#   STANDIN  Cloudflare's OTLP destination exporter. Local dev has no destinations, so
#          tools/standin_destination.mjs reads the spans Think recorded from wrangler's Local Explorer
#          and posts them to the collector as OTLP/HTTP JSON with the bearer header.
#
# Three legs, one Observe project each:
#   $FI_PROJECT_NAME          payloads off (Cloudflare default), collector content off: success + tool error + model error
#   $FI_PROJECT_NAME-guard    storeMessages/storeTools ON in the agent, collector content OFF: payloads must not arrive
#   $FI_PROJECT_NAME-optin    storeMessages/storeTools ON and FI_CAPTURE_CONTENT=true: payloads arrive
#
# Required env: FI_API_KEY FI_SECRET_KEY FI_TRACES_URL (as the collector container sees it, for example
#   http://host.docker.internal:4318/v1/traces for a local stack), OPENAI_BASE_URL OPENAI_API_KEY MODEL
#   (as workerd on this machine sees them).
# Optional: FI_PROJECT_NAME (default think-weather-e2e), PORT (8787), COLLECTOR_PORT (4318),
#   COLLECTOR_CONTAINER (think-otelcol-e2e), OTELCOL_IMAGE, EVIDENCE_DIR (./evidence),
#   VERIFY_CMD (run after each leg with the project name appended, e.g. a trace-read check),
#   SCAN=1 to run tools/scan_stored.py (needs docker access to the Future AGI Postgres and ClickHouse).
set -euo pipefail
cd "$(dirname "$0")"

: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_TRACES_URL:?}" "${OPENAI_BASE_URL:?}" "${OPENAI_API_KEY:?}" "${MODEL:?}"
PROJECT="${FI_PROJECT_NAME:-think-weather-e2e}"
PORT="${PORT:-8787}"
COLLECTOR_PORT="${COLLECTOR_PORT:-4318}"
CONTAINER="${COLLECTOR_CONTAINER:-think-otelcol-e2e}"
IMAGE="${OTELCOL_IMAGE:-otel/opentelemetry-collector-contrib:0.162.0}"
EVIDENCE="${EVIDENCE_DIR:-$PWD/evidence}"
mkdir -p "$EVIDENCE"
EXPLORER="http://127.0.0.1:$PORT"
ENDPOINT="http://127.0.0.1:$COLLECTOR_PORT/v1/traces"
RUN_ID="$(date +%s)"
MARKER="ZQT${RUN_ID}MK$((RANDOM % 9000 + 1000))"   # unique text that must not reach Future AGI with content off
echo "$MARKER" > "$EVIDENCE/marker-$RUN_ID.txt"
COLLECTOR_TOKEN="$(node -e 'console.log(require("crypto").randomBytes(24).toString("hex"))')"
export COLLECTOR_TOKEN
WRANGLER_PID=""

stop_collector() {
  if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    docker logs "$CONTAINER" >> "$EVIDENCE/otelcol-$RUN_ID.log" 2>&1 || true
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  [ -n "$WRANGLER_PID" ] && kill "$WRANGLER_PID" 2>/dev/null || true
  stop_collector
  rm -f .dev.vars
}
trap cleanup EXIT

# Model settings go to workerd through .dev.vars (never on the command line, never committed).
( umask 077; printf 'OPENAI_BASE_URL=%s\nOPENAI_API_KEY=%s\nMODEL=%s\n' "$OPENAI_BASE_URL" "$OPENAI_API_KEY" "$MODEL" > .dev.vars )

start_collector() { # project capture
  stop_collector
  docker run -d --name "$CONTAINER" --memory 256m -p "127.0.0.1:$COLLECTOR_PORT:4318" \
    -v "$PWD/otelcol.yaml:/etc/otelcol-contrib/config.yaml:ro" \
    -e COLLECTOR_TOKEN -e FI_API_KEY -e FI_SECRET_KEY -e FI_TRACES_URL \
    -e FI_PROJECT_NAME="$1" -e FI_CAPTURE_CONTENT="$2" "$IMAGE" >/dev/null
  for _ in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$ENDPOINT" -H 'content-type: application/json' -d '{}' || true)
    [ "$code" = "401" ] && return 0   # up, and refusing requests without the bearer token
    sleep 1
  done
  echo "collector did not start"; docker logs "$CONTAINER" | tail -20; return 1
}

start_wrangler() { # extra --var args...
  [ -n "$WRANGLER_PID" ] && { kill "$WRANGLER_PID" 2>/dev/null || true; sleep 2; }
  XDG_CONFIG_HOME="$PWD/.wrangler-home" WRANGLER_SEND_METRICS=false \
    ./node_modules/.bin/wrangler dev --ip 127.0.0.1 --port "$PORT" --inspector-port $((PORT + 500)) \
    --show-interactive-dev-session=false "$@" > "$EVIDENCE/wrangler-$RUN_ID.log" 2>&1 &
  WRANGLER_PID=$!
  for _ in $(seq 1 60); do grep -q "Ready on" "$EVIDENCE/wrangler-$RUN_ID.log" 2>/dev/null && return 0; sleep 1; done
  echo "wrangler dev did not start"; tail -20 "$EVIDENCE/wrangler-$RUN_ID.log"; return 1
}

turn() { # conversation text  -> prints the turn status
  curl -s -X POST "$EXPLORER/turn?conversation=$1&note=$MARKER" -H 'content-type: application/json' \
    -d "$(node -e 'console.log(JSON.stringify({text: process.argv[1]}))' "$2")"
  echo
}

forward() { # leg
  node tools/standin_destination.mjs --explorer "$EXPLORER" --endpoint "$ENDPOINT" --out "$EVIDENCE/wire-$1.json" | tee "$EVIDENCE/forward-$1.json"
}

verify() { # leg project
  if [ -n "${VERIFY_CMD:-}" ]; then $VERIFY_CMD "$2" | tee "$EVIDENCE/verify-$1.txt"; fi
}

wire_count() { # leg -> how often the marker was in what the stand-in exporter sent (before the collector)
  python3 -c 'import sys; print(open(sys.argv[1], encoding="utf-8").read().count(sys.argv[2]))' "$EVIDENCE/wire-$1.json" "$MARKER" | tee "$EVIDENCE/wire-count-$1.txt"
}

scan() { # leg project [--expect-found]   stored rows only, every column, after this leg's traces are stored
  [ "${SCAN:-0}" = "1" ] || return 0
  local leg="$1" p="$2"; shift 2
  local traces
  traces=$(node -e 'for (const t of JSON.parse(require("fs").readFileSync(process.argv[1])).trace_ids) console.log("--trace", t)' "$EVIDENCE/forward-$leg.json")
  # shellcheck disable=SC2086
  python3 tools/scan_stored.py --project "$p" --needle "marker=$MARKER" --json "$EVIDENCE/scan-$leg.json" --wait 300 $traces "$@"
  # never exported in any mode: keys, the collector token, and who/where this machine is
  local host; host="$(hostname -s)"
  # shellcheck disable=SC2086
  python3 tools/scan_stored.py --project "$p" --json "$EVIDENCE/scan-secrets-$leg.json" --wait 300 $traces \
    --wire "$EVIDENCE/wire-$leg.json" \
    --needle "fi_api_key=$FI_API_KEY" --needle "fi_secret_key=$FI_SECRET_KEY" --needle "model_key=$OPENAI_API_KEY" \
    --needle "collector_token=$COLLECTOR_TOKEN" --needle "user=$USER" --needle "home=$HOME" --needle "host=$host"
}

CITY="Lisbon-$MARKER"
ASK="What is the weather in the city named $CITY? Repeat the city name exactly in your answer."

echo "== leg 1: payloads off (default), project $PROJECT"
start_collector "$PROJECT" false
start_wrangler
curl -s -X POST "$EXPLORER/cdn-cgi/local/explorer/api/local/observability/clear" -H 'content-type: application/json' -d '{}' >/dev/null
turn "e2e-$RUN_ID-ok" "$ASK"
turn "e2e-$RUN_ID-toolerr" "What is the weather in Atlantis-$MARKER? Use the tool."
node tools/check_local_tree.mjs --explorer "$EXPLORER" --payloads off --tool --error-type Error --root-conversation --dump "$EVIDENCE/rows-default.json" | tee "$EVIDENCE/local-tree-default.json"
start_wrangler --var MODEL:no-such-model-e2e     # failure case: the model endpoint rejects the call
turn "e2e-$RUN_ID-modelerr" "$ASK"
node tools/check_local_tree.mjs --explorer "$EXPLORER" --payloads off --error-type AI_APICallError > "$EVIDENCE/local-tree-modelerr.json"
forward default
echo "marker occurrences sent to the collector (query strings): $(wire_count default)"
scan default "$PROJECT"
verify default "$PROJECT"

echo "== leg 2: storeMessages/storeTools on in the agent, collector content off, project $PROJECT-guard"
start_collector "$PROJECT-guard" false
start_wrangler --var THINK_STORE_PAYLOADS:true
curl -s -X POST "$EXPLORER/cdn-cgi/local/explorer/api/local/observability/clear" -H 'content-type: application/json' -d '{}' >/dev/null
turn "e2e-$RUN_ID-guard" "$ASK"
node tools/check_local_tree.mjs --explorer "$EXPLORER" --payloads on --tool --root-conversation --dump "$EVIDENCE/rows-guard.json" | tee "$EVIDENCE/local-tree-guard.json"
forward guard
echo "marker occurrences sent to the collector (payloads): $(wire_count guard)"   # Cloudflare recorded them
scan guard "$PROJECT-guard"   # ...and the stored rows must not have them
verify guard "$PROJECT-guard"

echo "== leg 3: opt-in (storeMessages/storeTools on + FI_CAPTURE_CONTENT=true), project $PROJECT-optin"
start_collector "$PROJECT-optin" true
curl -s -X POST "$EXPLORER/cdn-cgi/local/explorer/api/local/observability/clear" -H 'content-type: application/json' -d '{}' >/dev/null
turn "e2e-$RUN_ID-optin" "$ASK"
node tools/check_local_tree.mjs --explorer "$EXPLORER" --payloads on --tool > "$EVIDENCE/local-tree-optin.json"
forward optin
echo "marker occurrences sent to the collector: $(wire_count optin)"
scan optin "$PROJECT-optin" --expect-found
verify optin "$PROJECT-optin"

echo "E2E OK  run=$RUN_ID  evidence=$EVIDENCE"
