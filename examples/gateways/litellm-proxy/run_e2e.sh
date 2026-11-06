#!/usr/bin/env bash
# Run LiteLLM Proxy for real, send requests through it, and check what it exports.
#
#   ./run_e2e.sh                                  # proxy + mock upstream + local OTLP sink: no keys, no spend
#   TARGET=futureagi FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 ./run_e2e.sh
#
# Settings (environment):
#   RUNNER            docker (default; official image) | pip (creates ./.venv-e2e from requirements.txt)
#   LITELLM_VERSION   1.105.1 (the version this recipe was tested with)
#   MODE              v2 (default; LITELLM_OTEL_V2=true) | v1 (the legacy "otel" callback)
#   CONTENT           off (default; NO_CONTENT) | on (SPAN_ONLY)
#   TARGET            sink (default; records the export and checks it) | futureagi (sends it to Future AGI)
#   FI_PROJECT_NAME   project_name resource attribute (default litellm-proxy-e2e); NO_PROJECT=1 leaves it out
#   SCENARIOS         comma list for send_requests.py (default: all that the upstream supports)
#   UPSTREAM          mock (default) | real  (real: set UPSTREAM_MODEL / UPSTREAM_API_BASE / UPSTREAM_API_KEY)
#   MOCK_PORT / SINK_PORT / PROXY_PORT   18081 / 14390 / 4000
#   START_TIMEOUT     seconds to wait for the proxy to answer (default 300; the first docker start can take minutes)
#   COLLECTOR         none (default) | scrub (put collector/otelcol-scrub.yaml between the proxy and the target)
#   KEEP=1            leave the proxy container running when done
#
# Containers it starts are removed on exit. Nothing is sent anywhere but the endpoint you choose.
set -euo pipefail

case "${1:-}" in -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;; esac

HERE="$(cd "$(dirname "$0")" && pwd)"
RUNNER="${RUNNER:-docker}"
LITELLM_VERSION="${LITELLM_VERSION:-1.105.1}"
MODE="${MODE:-v2}"
CONTENT="${CONTENT:-off}"
TARGET="${TARGET:-sink}"
UPSTREAM="${UPSTREAM:-mock}"
MOCK_PORT="${MOCK_PORT:-18081}"
SINK_PORT="${SINK_PORT:-14390}"
PROXY_PORT="${PROXY_PORT:-4000}"
NAME_PREFIX="${NAME_PREFIX:-litellm-otel-e2e}"
IMAGE="${LITELLM_IMAGE:-ghcr.io/berriai/litellm:v${LITELLM_VERSION}}"
FLUSH_WAIT="${FLUSH_WAIT:-12}"
OUT="${OUT:-$HERE/out/$(date +%Y%m%d-%H%M%S)}"
MARKER="${MARKER:-MARK_$(python3 -c 'import secrets; print(secrets.token_hex(5))')}"
MASTER_KEY="sk-e2e-$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
mkdir -p "$OUT/captures"
PIDS=()
CONTAINERS=()

cleanup() {
  local rc=$?
  if [ "${KEEP:-0}" != "1" ]; then
    for c in "${CONTAINERS[@]:-}"; do if [ -n "$c" ]; then docker rm -f "$c" >/dev/null 2>&1 || true; fi; done
  fi
  for p in "${PIDS[@]:-}"; do if [ -n "$p" ]; then kill "$p" >/dev/null 2>&1 || true; fi; done
  exit $rc
}
trap cleanup EXIT

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 2; }; }
need python3; need curl
if [ "$RUNNER" = docker ]; then need docker; fi

# host name the proxy uses to reach things running on this machine
if [ "$RUNNER" = docker ]; then HOST_ALIAS="host.docker.internal"; else HOST_ALIAS="127.0.0.1"; fi

# ---------------------------------------------------------------- python for the sink (needs protobuf)
if [ "$RUNNER" = pip ]; then
  VENV="$HERE/.venv-e2e"
  if [ ! -x "$VENV/bin/litellm" ]; then
    echo "creating $VENV from requirements.txt (python3 must be 3.10 to 3.14; 3.12 was tested)"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$HERE/requirements.txt"
  fi
fi

# ---------------------------------------------------------------- mock upstream
if [ "$UPSTREAM" = mock ]; then
  python3 "$HERE/mock_upstream.py" --port "$MOCK_PORT" >"$OUT/mock.log" 2>&1 &
  PIDS+=($!)
  export UPSTREAM_MODEL="openai/mock-model" UPSTREAM_API_KEY="sk-mock"
  export UPSTREAM_API_BASE="http://$HOST_ALIAS:$MOCK_PORT/v1"
  DEFAULT_SCENARIOS="plain,stream,tools,error,unreachable,joined,headers,badkey"
else
  : "${UPSTREAM_MODEL:?set UPSTREAM_MODEL (for example openai/gpt-4o-mini)}" "${UPSTREAM_API_BASE:?set UPSTREAM_API_BASE}" "${UPSTREAM_API_KEY:?set UPSTREAM_API_KEY}"
  DEFAULT_SCENARIOS="plain,stream,tools,unreachable,joined,headers,badkey"
fi
SCENARIOS="${SCENARIOS:-$DEFAULT_SCENARIOS}"

# ---------------------------------------------------------------- where the proxy exports to
for_docker() { echo "$1" | sed -E 's#//(localhost|127\.0\.0\.1)#//host.docker.internal#'; }
if [ "$TARGET" = futureagi ]; then
  : "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL, for example http://localhost:4318}"
  FINAL_URL="${FI_BASE_URL%/}${FI_TRACES_PATH:-/v1/traces}"
  FINAL_KEY="$FI_API_KEY"; FINAL_SECRET="$FI_SECRET_KEY"
else
  FINAL_URL="http://127.0.0.1:$SINK_PORT/v1/traces"
  FINAL_KEY="sink-key"; FINAL_SECRET="sink-secret"
  if [ "$RUNNER" = docker ] || [ "${COLLECTOR:-none}" = scrub ]; then
    need docker
    SINK_C="$NAME_PREFIX-sink"; CONTAINERS+=("$SINK_C")
    docker rm -f "$SINK_C" >/dev/null 2>&1 || true
    docker run -d --name "$SINK_C" --memory 256m -p "127.0.0.1:$SINK_PORT:$SINK_PORT" \
      -v "$HERE:/ex:ro" -v "$OUT/captures:/captures" --entrypoint /app/.venv/bin/python "$IMAGE" \
      /ex/otlp_sink.py --host 0.0.0.0 --port "$SINK_PORT" --out /captures >/dev/null
  else
    "$VENV/bin/python" "$HERE/otlp_sink.py" --port "$SINK_PORT" --out "$OUT/captures" >"$OUT/sink.log" 2>&1 &
    PIDS+=($!)
  fi
fi
HEADERS="X-Api-Key=${FINAL_KEY},X-Secret-Key=${FINAL_SECRET}"
if [ "$RUNNER" = docker ]; then ENDPOINT="$(for_docker "$FINAL_URL")"; else ENDPOINT="$FINAL_URL"; fi

# optional: an OpenTelemetry Collector between the proxy and Future AGI that scrubs error text, stack traces and addresses
if [ "${COLLECTOR:-none}" = scrub ]; then
  need docker
  COLLECTOR_PORT="${COLLECTOR_PORT:-14391}"
  COL_C="$NAME_PREFIX-otelcol"; CONTAINERS+=("$COL_C")
  docker rm -f "$COL_C" >/dev/null 2>&1 || true
  docker run -d --name "$COL_C" --memory 256m --add-host host.docker.internal:host-gateway \
    -p "127.0.0.1:$COLLECTOR_PORT:4318" -v "$HERE/collector/otelcol-scrub.yaml:/etc/otelcol/config.yaml:ro" \
    -e FI_TRACES_ENDPOINT="$(for_docker "$FINAL_URL")" -e FI_API_KEY="$FINAL_KEY" -e FI_SECRET_KEY="$FINAL_SECRET" \
    "otel/opentelemetry-collector-contrib:${OTELCOL_VERSION:-0.162.0}" --config /etc/otelcol/config.yaml >/dev/null
  ENDPOINT="http://$HOST_ALIAS:$COLLECTOR_PORT/v1/traces"
  HEADERS=""
fi

PROJECT="${FI_PROJECT_NAME:-litellm-proxy-e2e}"
RES_ATTRS="project_name=$PROJECT,project_type=observe"
[ "${NO_PROJECT:-0}" = 1 ] && RES_ATTRS=""
CAPTURE_MODE="NO_CONTENT"; [ "$CONTENT" = on ] && CAPTURE_MODE="SPAN_ONLY"

ENVFILE="$OUT/proxy.env"; : >"$ENVFILE"; chmod 600 "$ENVFILE"
{
  echo "LITELLM_MASTER_KEY=$MASTER_KEY"
  echo "UPSTREAM_MODEL=$UPSTREAM_MODEL"
  echo "UPSTREAM_API_BASE=$UPSTREAM_API_BASE"
  echo "UPSTREAM_API_KEY=$UPSTREAM_API_KEY"
  echo "OTEL_EXPORTER=otlp_http"
  echo "OTEL_ENDPOINT=$ENDPOINT"
  if [ -n "$HEADERS" ]; then echo "OTEL_HEADERS=$HEADERS"; fi
  if [ -n "$RES_ATTRS" ]; then echo "OTEL_RESOURCE_ATTRIBUTES=$RES_ATTRS"; fi
  echo "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=$CAPTURE_MODE"
  if [ "$MODE" = v2 ]; then echo "LITELLM_OTEL_V2=true"; fi
  if [ -n "${EXTRA_ENV:-}" ]; then printf '%s\n' ${EXTRA_ENV}; fi
} >>"$ENVFILE"

# ---------------------------------------------------------------- the proxy
PROXY_URL="http://127.0.0.1:$PROXY_PORT"
if [ "$RUNNER" = docker ]; then
  PROXY_C="$NAME_PREFIX-proxy"; CONTAINERS+=("$PROXY_C")
  docker rm -f "$PROXY_C" >/dev/null 2>&1 || true
  docker run -d --name "$PROXY_C" --memory "${PROXY_MEMORY:-768m}" --add-host host.docker.internal:host-gateway \
    -p "127.0.0.1:$PROXY_PORT:4000" --env-file "$ENVFILE" -v "$HERE/config.yaml:/app/config.yaml:ro" \
    "$IMAGE" --config /app/config.yaml --port 4000 >/dev/null
else
  ( set -a; . "$ENVFILE"; set +a; exec "$VENV/bin/litellm" --config "$HERE/config.yaml" --host 127.0.0.1 --port "$PROXY_PORT" ) >"$OUT/proxy.log" 2>&1 &
  PIDS+=($!)
fi
echo "waiting for the proxy on $PROXY_URL ..."
for _ in $(seq 1 ${START_TIMEOUT:-300}); do curl -fs -o /dev/null "$PROXY_URL/health/liveliness" && break; sleep 1; done
if ! curl -fs -o /dev/null "$PROXY_URL/health/liveliness"; then
  echo "proxy did not start" >&2
  if [ "$RUNNER" = docker ]; then docker logs "$PROXY_C" 2>&1 | tail -30; else tail -30 "$OUT/proxy.log"; fi
  exit 1
fi

# ---------------------------------------------------------------- requests
echo "mode=$MODE content=$CONTENT target=$TARGET runner=$RUNNER version=$LITELLM_VERSION project=$PROJECT marker=$MARKER"
python3 "$HERE/send_requests.py" --proxy "$PROXY_URL" --key "$MASTER_KEY" --marker "$MARKER" --only "$SCENARIOS" | tee "$OUT/scenarios.jsonl"
echo "waiting ${FLUSH_WAIT}s for the batch exporter ..."
sleep "$FLUSH_WAIT"
if [ "$RUNNER" = docker ]; then docker logs "$PROXY_C" >"$OUT/proxy.log" 2>&1 || true; fi

# ---------------------------------------------------------------- verdict
if [ "$TARGET" = sink ]; then
  echo; echo "checking what the proxy exported:"
  SCRUB_FLAG=""; if [ "${COLLECTOR:-none}" = scrub ]; then SCRUB_FLAG="--scrubbed"; fi
  python3 "$HERE/otlp_contract.py" check "$OUT/captures" --mode "$MODE" --content "$CONTENT" --marker "$MARKER" --master-key "$MASTER_KEY" $SCRUB_FLAG
  echo; echo "capture: $OUT/captures   (requests.jsonl lists every request the proxy made)"
else
  echo; echo "Exported to $ENDPOINT as project '$PROJECT'. Open Observe and select that project."
  echo "Look for the marker $MARKER (content off: it must NOT appear; content on: it appears in gen_ai.input.messages)."
  grep -i "Failed to export" "$OUT/proxy.log" | head -3 || true
fi
