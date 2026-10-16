# shared helpers for run_e2e.sh (sourced). Containers are named ${PREFIX}-*.
GRAVITEE_VERSION="${GRAVITEE_VERSION:-4.12.23}"
OTELCOL_VERSION="${OTELCOL_VERSION:-0.162.0}"
MONGO_IMAGE="${MONGO_IMAGE:-mongo:6.0.8}"            # the version Gravitee's own compose file pins
PREFIX="${PREFIX:-gravitee-fi-e2e}"
NET="${PREFIX}-net"
GW_PORT="${GW_PORT:-18082}"
MAPI_PORT="${MAPI_PORT:-18083}"
BACKEND_PORT="${BACKEND_PORT:-18090}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVID="${EVID:-$HERE/.evidence}"
PY="${PY:-python3}"
mkdir -p "$EVID"
MONGO_URI='mongodb://mongodb:27017/gravitee?serverSelectionTimeoutMS=5000&connectTimeoutMS=5000&socketTimeoutMS=5000'

start_mongo() {
  docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
  docker ps --format '{{.Names}}' | grep -qx "$PREFIX-mongo" && return 0
  docker rm -f "$PREFIX-mongo" >/dev/null 2>&1 || true
  docker run -d --name "$PREFIX-mongo" --network "$NET" --network-alias mongodb --memory 384m \
    "$MONGO_IMAGE" --wiredTigerCacheSizeGB 0.25 >/dev/null
}
# Management API: only needed to create/deploy the APIs, then stopped to save memory.
start_mapi() {
  docker rm -f "$PREFIX-mapi" >/dev/null 2>&1 || true
  docker run -d --name "$PREFIX-mapi" --network "$NET" --memory 768m -p "127.0.0.1:$MAPI_PORT:8083" \
    -e "gravitee_management_mongodb_uri=$MONGO_URI" -e gravitee_repositories_analytics_type=none \
    "graviteeio/apim-management-api:$GRAVITEE_VERSION" >/dev/null
  for _ in $(seq 1 90); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' -u admin:admin "http://127.0.0.1:$MAPI_PORT/management/organizations/DEFAULT/environments/DEFAULT/apis")" = 200 ] && return 0
    sleep 2
  done
  echo "Management API did not become ready" >&2; docker logs "$PREFIX-mapi" 2>&1 | tail -20 >&2; return 1
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
    "otel/opentelemetry-collector-contrib:$OTELCOL_VERSION" --config /etc/otelcol/config.yaml >/dev/null
  sleep 3
  docker ps --format '{{.Names}}' | grep -qx "$PREFIX-otelcol" || { docker logs "$PREFIX-otelcol" 2>&1 | tail -20 >&2; return 1; }
}
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
  for _ in $(seq 1 90); do
    # poll the untraced API: the Gateway answers 404 until its sync has loaded the APIs
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$GW_PORT/fi-untraced/")" = 200 ]; then sleep 2; return 0; fi
    docker ps --format '{{.Names}}' | grep -qx "$PREFIX-gw" || break
    sleep 2
  done
  echo "Gateway did not serve /fi-untraced/" >&2; docker logs "$PREFIX-gw" 2>&1 | tail -30 >&2; return 1
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
