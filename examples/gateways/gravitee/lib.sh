# shared helpers for run_e2e.sh (sourced). Containers are named ${PREFIX}-*.
GRAVITEE_VERSION="${GRAVITEE_VERSION:-4.12.23}"
OTELCOL_VERSION="${OTELCOL_VERSION:-0.162.0}"
MONGO_IMAGE="${MONGO_IMAGE:-mongo:6.0.8}"            # the version Gravitee's own compose file pins
PREFIX="${PREFIX:-gravitee-fi-e2e}"
NET="${PREFIX}-net"
GW_PORT="${GW_PORT:-18082}"
MAPI_PORT="${MAPI_PORT:-18083}"
BACKEND_PORT="${BACKEND_PORT:-18090}"
OTELCOL_PORT="${OTELCOL_PORT:-18084}"        # loopback port of the Collector's OTLP/HTTP receiver (readiness probe only)
# Readiness waits poll each component's own readiness signal. A loaded host can need minutes (the JVM services
# took over 180 s at load average 50-70), so the default is 10 minutes; a container that exits fails at once.
READY_TIMEOUT="${READY_TIMEOUT:-600}"        # seconds, default for every wait below
MONGO_READY_TIMEOUT="${MONGO_READY_TIMEOUT:-$READY_TIMEOUT}"
MAPI_READY_TIMEOUT="${MAPI_READY_TIMEOUT:-$READY_TIMEOUT}"
GW_READY_TIMEOUT="${GW_READY_TIMEOUT:-$READY_TIMEOUT}"
OTELCOL_READY_TIMEOUT="${OTELCOL_READY_TIMEOUT:-$READY_TIMEOUT}"
GW_API_GRACE="${GW_API_GRACE:-30}"           # seconds the deployed test API may lag behind the Gateway's sync probe
READY_POLL="${READY_POLL:-2}"                # seconds between polls
LOG_TAIL="${LOG_TAIL:-80}"                   # container log lines printed when a wait fails
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVID="${EVID:-$HERE/.evidence}"
PY="${PY:-python3}"
mkdir -p "$EVID"
MONGO_URI='mongodb://mongodb:27017/gravitee?serverSelectionTimeoutMS=5000&connectTimeoutMS=5000&socketTimeoutMS=5000'

# wait_ready <label> <container> <TIMEOUT_VAR> <probe command...>: run the probe until it succeeds. Stops at once if
# the container is no longer running; after ${TIMEOUT_VAR} seconds gives up. Either way prints the container's last
# log lines (key values redacted) and returns 1. The time to readiness is appended to $EVID/readiness.txt.
wait_ready() {
  local label=$1 c=$2 tvar=$3 start=$SECONDS state timeout; shift 3
  timeout=${!tvar}
  while :; do
    if "$@" >/dev/null 2>&1; then
      echo "$label ready after $((SECONDS - start))s" | tee -a "$EVID/readiness.txt"
      return 0
    fi
    state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo missing)
    if [ "$state" != running ]; then
      echo "$label did not become ready: container $c is $state after $((SECONDS - start))s" >&2
      break
    fi
    if [ $((SECONDS - start)) -gt "$timeout" ]; then   # SECONDS ticks in whole seconds: wait at least the timeout
      echo "$label did not become ready within ${timeout}s (raise $tvar or READY_TIMEOUT on a slow host)" >&2
      break
    fi
    sleep "$READY_POLL"
  done
  print_logs "$c"
  return 1
}
print_logs() {
  echo "--- last $LOG_TAIL lines of the $1 log (key values redacted) ---" >&2
  docker logs --tail "$LOG_TAIL" "$1" 2>&1 | redact_secrets >&2 || true
}
# redact_secrets: stdin to stdout with the Future AGI keys, the Collector token and the LLM key replaced
redact_secrets() {
  R1="${FI_API_KEY:-}" R2="${FI_SECRET_KEY:-}" R3="${GATEWAY_TOKEN:-}" R4="${LLM_API_KEY:-}" "$PY" -c 'import os, sys
vals = [v for v in (os.environ.get(k, "") for k in ("R1", "R2", "R3", "R4")) if len(v) >= 4]
for line in sys.stdin:
    for v in vals:
        line = line.replace(v, "<redacted>")
    sys.stdout.write(line)'
}
http_code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$@" 2>/dev/null || true; }

# MongoDB answers a ping (mongosh ships in the mongo image)
mongo_ready() { docker exec "$PREFIX-mongo" mongosh --quiet --eval 'quit(db.runCommand({ ping: 1 }).ok === 1 ? 0 : 1)'; }
start_mongo() {
  docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
  if ! docker ps --format '{{.Names}}' | grep -qx "$PREFIX-mongo"; then
    docker rm -f "$PREFIX-mongo" >/dev/null 2>&1 || true
    docker run -d --name "$PREFIX-mongo" --network "$NET" --network-alias mongodb --memory 384m \
      "$MONGO_IMAGE" --wiredTigerCacheSizeGB 0.25 >/dev/null
  fi
  wait_ready MongoDB "$PREFIX-mongo" MONGO_READY_TIMEOUT mongo_ready
}
# Management API ready: its health endpoint (internal API, inside the container, image-default credentials) is 200,
# and the REST API the run uses answers 200 for the admin user.
mapi_ready() {
  docker exec "$PREFIX-mapi" curl -fs -m 5 -u admin:adminadmin http://localhost:18083/_node/health | probes_healthy &&
    [ "$(http_code -u admin:admin "http://127.0.0.1:$MAPI_PORT/management/organizations/DEFAULT/environments/DEFAULT/apis")" = 200 ]
}
# Management API: only needed to create/deploy the APIs, then stopped to save memory.
start_mapi() {
  docker rm -f "$PREFIX-mapi" >/dev/null 2>&1 || true
  docker run -d --name "$PREFIX-mapi" --network "$NET" --memory 768m -p "127.0.0.1:$MAPI_PORT:8083" \
    -e "gravitee_management_mongodb_uri=$MONGO_URI" -e gravitee_repositories_analytics_type=none \
    "graviteeio/apim-management-api:$GRAVITEE_VERSION" >/dev/null
  wait_ready "Management API" "$PREFIX-mapi" MAPI_READY_TIMEOUT mapi_ready
}
stop_mapi() { docker rm -f "$PREFIX-mapi" >/dev/null 2>&1 || true; }

# render <out.yml> [render_gateway_config.py args]: merge the shipped snippet into the image's own gravitee.yml
render() {
  local out="$1"; shift
  [ -s "$EVID/gravitee.default.yml" ] || docker run --rm --entrypoint cat "graviteeio/apim-gateway:$GRAVITEE_VERSION" \
      /opt/graviteeio-gateway/config/gravitee.yml > "$EVID/gravitee.default.yml"
  "$PY" "$HERE/render_gateway_config.py" --base "$EVID/gravitee.default.yml" --snippet "$HERE/gravitee-opentelemetry.yml" --out "$out" "$@"
}

# start_otelcol: otelcol.yaml with the Future AGI keys, project and Gateway token from this shell's environment
start_otelcol() {
  docker rm -f "$PREFIX-otelcol" >/dev/null 2>&1 || true
  docker run -d --name "$PREFIX-otelcol" --network "$NET" --network-alias otel-collector --memory 256m \
    --add-host host.docker.internal:host-gateway \
    -e GATEWAY_TOKEN -e FI_API_KEY -e FI_SECRET_KEY -e FI_PROJECT_NAME -e FI_TRACES_URL -e FI_CAPTURE_CONTENT \
    -v "$HERE/otelcol.yaml:/etc/otelcol/config.yaml:ro" \
    -p "127.0.0.1:$OTELCOL_PORT:4318" \
    "otel/opentelemetry-collector-contrib:$OTELCOL_VERSION" --config /etc/otelcol/config.yaml >/dev/null
  wait_ready Collector "$PREFIX-otelcol" OTELCOL_READY_TIMEOUT otelcol_ready
}
# Collector ready: its OTLP/HTTP receiver answers. Receivers start last, after the exporter and processors, and
# the bearer-token authenticator rejects this unauthenticated probe with 401, so nothing is forwarded.
otelcol_ready() { [ "$(http_code -X POST "http://127.0.0.1:$OTELCOL_PORT/v1/traces")" = 401 ]; }
stop_otelcol() { docker stop -t 15 "$PREFIX-otelcol" >/dev/null 2>&1 || true; docker rm -f "$PREFIX-otelcol" >/dev/null 2>&1 || true; }

# start_gateway <rendered gravitee.yml>: the real APIM Gateway. Exporter header values come only from
# environment variables (gravitee_services_opentelemetry_exporter_headers_N_name / _value) passed through by name.
start_gateway() {
  docker rm -f "$PREFIX-gw" >/dev/null 2>&1 || true
  docker run -d --name "$PREFIX-gw" --network "$NET" --memory 768m -p "127.0.0.1:$GW_PORT:8082" \
    --add-host host.docker.internal:host-gateway \
    -e "gravitee_management_mongodb_uri=$MONGO_URI" -e "gravitee_ratelimit_mongodb_uri=$MONGO_URI" \
    -e gravitee_reporters_elasticsearch_enabled=false \
    -e gravitee_services_opentelemetry_exporter_endpoint -e gravitee_services_opentelemetry_verbose \
    -e gravitee_services_opentelemetry_exporter_headers_0_name -e gravitee_services_opentelemetry_exporter_headers_0_value \
    -e gravitee_services_opentelemetry_exporter_headers_1_name -e gravitee_services_opentelemetry_exporter_headers_1_value \
    ${GW_EXTRA_ARGS:-} \
    -v "$1:/opt/graviteeio-gateway/config/gravitee.yml:ro" "graviteeio/apim-gateway:$GRAVITEE_VERSION" >/dev/null
  wait_ready Gateway "$PREFIX-gw" GW_READY_TIMEOUT gw_ready || return 1
  # sync done means the deployed APIs are loaded: the untraced API (tracing off, so it adds no span) must answer now.
  # A wrong HTTP answer (404: API not deployed) fails after GW_API_GRACE seconds. No answer within curl's 5 s (code
  # 000, a slow first request on a loaded host) does not use up the grace; it is bounded by GW_READY_TIMEOUT.
  local code start=$SECONDS answered=
  while :; do
    code=$(http_code "http://127.0.0.1:$GW_PORT/fi-untraced/")
    [ "$code" = 200 ] && return 0
    [ "$code" != 000 ] && [ -z "$answered" ] && answered=$SECONDS
    [ -n "$answered" ] && [ $((SECONDS - answered)) -gt "$GW_API_GRACE" ] && break
    [ $((SECONDS - start)) -gt "$GW_READY_TIMEOUT" ] && break
    sleep "$READY_POLL"
  done
  if [ "$code" = 000 ]; then
    echo "Gateway is ready (sync-process healthy) but /fi-untraced/ did not answer within ${GW_READY_TIMEOUT}s (raise GW_READY_TIMEOUT or READY_TIMEOUT on a slow host)" >&2
  else
    echo "Gateway is ready (sync-process healthy) but /fi-untraced/ answers HTTP $code: the test APIs are not deployed" >&2
  fi
  print_logs "$PREFIX-gw"
  return 1
}
# Gateway ready: its health endpoint (internal API, inside the container, image-default credentials) reports the
# HTTP server up and the initial sync done (APIs, platform policies, properties, dictionaries loaded).
gw_ready() {
  docker exec "$PREFIX-gw" curl -fs -m 5 -u admin:adminadmin "http://localhost:18082/_node/health?probes=http-server,sync-process" |
    probes_healthy http-server sync-process
}
# probes_healthy [probe...]: a /_node/health JSON body on stdin has every named probe (or, with none named, every
# probe it lists) present with "healthy": true. An unknown probe name is missing from the body, so it never passes.
probes_healthy() {
  "$PY" -c 'import json, sys
d = json.load(sys.stdin)
names = sys.argv[1:] or list(d)
sys.exit(0 if names and all(isinstance(d.get(n), dict) and d[n].get("healthy") is True for n in names) else 1)' "$@"
}
stop_gateway() {
  # docker stop sends SIGTERM: the Gateway's BatchSpanProcessor flushes pending spans on shutdown
  docker stop -t 30 "$PREFIX-gw" >/dev/null 2>&1 || true
}
rm_gateway() { docker rm -f "$PREFIX-gw" >/dev/null 2>&1 || true; }
cleanup_all() { rm_gateway; stop_mapi; stop_otelcol; docker rm -f "$PREFIX-mongo" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; }

# AC: secret values never appear in the Gateway or Collector logs
assert_no_secrets_in_logs() {
  local c
  for c in "$PREFIX-gw" "$PREFIX-otelcol"; do
    docker ps -a --format '{{.Names}}' | grep -qx "$c" || continue
    if docker logs "$c" 2>&1 | grep -qF -e "${FI_SECRET_KEY}" -e "${FI_API_KEY}" -e "${GATEWAY_TOKEN:-unset-token}" -e "${LLM_API_KEY:-unset-llm-key}"; then
      echo "SECRET FOUND in $c logs" >&2; return 1; fi
    echo "$c logs: no key/token values ($(docker logs "$c" 2>&1 | wc -l | tr -d ' ') lines checked)"
  done
}
tp() { echo "00-$($PY -c 'import uuid;print(uuid.uuid4().hex)')-$($PY -c 'import uuid;print(uuid.uuid4().hex[:16])')-01"; }
