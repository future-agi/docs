# shared helpers for run_e2e.sh and capture_fixtures.sh (sourced)
KONG_IMAGE="${KONG_IMAGE:-kong/kong-gateway:3.16.0.1}"
KONG_CONTAINER="${KONG_CONTAINER:-kong-fi-e2e}"
KONG_PROXY_PORT="${KONG_PROXY_PORT:-18010}"
KONG_ADMIN_PORT="${KONG_ADMIN_PORT:-18011}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVID="${EVID:-$HERE/.evidence}"
mkdir -p "$EVID"

# start_kong <rendered-config>  -- DB-less Kong, tracing on, small footprint
start_kong() {
  docker rm -f "$KONG_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$KONG_CONTAINER" --memory 768m \
    -p "$KONG_PROXY_PORT:8000" -p "127.0.0.1:$KONG_ADMIN_PORT:8001" \
    -e KONG_DATABASE=off -e KONG_DECLARATIVE_CONFIG=/kong/kong.yml \
    -e KONG_ADMIN_LISTEN=0.0.0.0:8001 \
    -e KONG_TRACING_INSTRUMENTATIONS=request -e KONG_TRACING_SAMPLING_RATE=1.0 \
    -e KONG_NGINX_WORKER_PROCESSES=1 -e KONG_LMDB_MAP_SIZE=64m -e KONG_MEM_CACHE_SIZE=32m \
    ${KONG_EXTRA_ARGS:-} \
    -v "$1:/kong/kong.yml:ro" "$KONG_IMAGE" >/dev/null
  for _ in $(seq 1 60); do
    curl -fs "http://127.0.0.1:$KONG_ADMIN_PORT/status" >/dev/null 2>&1 && { sleep 6; return 0; }   # /status is up slightly before the proxy router
    sleep 1
  done
  echo "Kong did not become ready" >&2; docker logs "$KONG_CONTAINER" 2>&1 | tail -20 >&2; return 1
}
# AC: secret header values never appear in the gateway logs
assert_no_secrets_in_logs() {
  if docker logs "$KONG_CONTAINER" 2>&1 | grep -qF -e "${FI_SECRET_KEY}" -e "${FI_API_KEY}" -e "${UPSTREAM_API_KEY}"; then
    echo "SECRET FOUND in Kong logs" >&2; return 1; fi
  echo "kong logs: no FI/upstream secret values ($(docker logs "$KONG_CONTAINER" 2>&1 | wc -l | tr -d ' ') lines checked)"
}
stop_kong() { docker rm -f "$KONG_CONTAINER" >/dev/null 2>&1 || true; }

# render <out> : envsubst the declarative config (keeps secrets out of the repo)
render() {
  # shellcheck disable=SC2016
  envsubst '${UPSTREAM_API_KEY} ${UPSTREAM_MODEL} ${UPSTREAM_CHAT_URL} ${LOG_PAYLOADS} ${FI_TRACES_ENDPOINT} ${FI_API_KEY} ${FI_SECRET_KEY} ${FI_PROJECT_NAME}' \
    < "$HERE/kong.yml" > "$1"
  chmod 600 "$1"
}

# chat <prompt> [traceparent]
chat() {
  local body; local -a hdr=(-H 'content-type: application/json')
  body=$(python3 -c 'import json,sys;print(json.dumps({"messages":[{"role":"user","content":sys.argv[1]}]}))' "$1")
  [ -n "${2:-}" ] && hdr+=(-H "traceparent: $2")
  curl -s -m 90 -w '\nHTTP %{http_code}\n' "http://127.0.0.1:$KONG_PROXY_PORT/chat" "${hdr[@]}" -d "$body"
}
