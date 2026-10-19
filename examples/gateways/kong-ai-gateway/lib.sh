# shared helpers for run_e2e.sh and capture_fixtures.sh (sourced)
KONG_IMAGE="${KONG_IMAGE:-kong/kong-gateway:3.16.0.1}"
KONG_CONTAINER="${KONG_CONTAINER:-kong-fi-e2e}"
KONG_PROXY_PORT="${KONG_PROXY_PORT:-18010}"
KONG_ADMIN_PORT="${KONG_ADMIN_PORT:-18011}"
KONG_STATUS_PORT="${KONG_STATUS_PORT:-18012}"       # Kong Status API (GET /status/ready), loopback only
KONG_READY_TIMEOUT="${KONG_READY_TIMEOUT:-300}"     # seconds to wait for /status/ready; a loaded host needs minutes
KONG_READY_POLL="${KONG_READY_POLL:-2}"             # seconds between readiness polls
KONG_LOG_TAIL="${KONG_LOG_TAIL:-60}"                # Kong log lines printed when it does not become ready
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVID="${EVID:-$HERE/.evidence}"
mkdir -p "$EVID"

# start_kong <rendered-config>  -- DB-less Kong, tracing on, small footprint
start_kong() {
  docker rm -f "$KONG_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$KONG_CONTAINER" --memory 768m \
    -p "$KONG_PROXY_PORT:8000" -p "127.0.0.1:$KONG_ADMIN_PORT:8001" -p "127.0.0.1:$KONG_STATUS_PORT:8007" \
    -e KONG_DATABASE=off -e KONG_DECLARATIVE_CONFIG=/kong/kong.yml \
    -e KONG_ADMIN_LISTEN=0.0.0.0:8001 -e KONG_STATUS_LISTEN=0.0.0.0:8007 \
    -e KONG_TRACING_INSTRUMENTATIONS=request -e KONG_TRACING_SAMPLING_RATE=1.0 \
    -e KONG_NGINX_WORKER_PROCESSES=1 -e KONG_LMDB_MAP_SIZE=64m -e KONG_MEM_CACHE_SIZE=32m \
    ${KONG_EXTRA_ARGS:-} \
    -v "$1:/kong/kong.yml:ro" "$KONG_IMAGE" >/dev/null
  wait_kong_ready
}
# wait_kong_ready: poll Kong's readiness endpoint, GET /status/ready on the Status API. It answers 200 only once
# the declarative config is loaded and the router and plugins are built in every worker (503 before that), so the
# proxy can take traffic. Fails at once if the container stops; on timeout prints Kong's last log lines.
wait_kong_ready() {
  local start=$SECONDS state
  while :; do
    if curl -fs -m 5 -o /dev/null "http://127.0.0.1:$KONG_STATUS_PORT/status/ready" 2>/dev/null; then
      echo "Kong ready after $((SECONDS - start))s (GET /status/ready = 200)" | tee -a "$EVID/readiness.txt"
      return 0
    fi
    state=$(docker inspect -f '{{.State.Status}}' "$KONG_CONTAINER" 2>/dev/null || echo missing)
    if [ "$state" != running ]; then
      echo "Kong did not become ready: container $KONG_CONTAINER is $state after $((SECONDS - start))s" >&2
      break
    fi
    if [ $((SECONDS - start)) -gt "$KONG_READY_TIMEOUT" ]; then   # SECONDS ticks in whole seconds: wait at least the timeout
      echo "Kong did not become ready within ${KONG_READY_TIMEOUT}s (GET /status/ready never returned 200; raise KONG_READY_TIMEOUT on a slow host)" >&2
      break
    fi
    sleep "$KONG_READY_POLL"
  done
  echo "--- last $KONG_LOG_TAIL lines of the $KONG_CONTAINER log (key values redacted) ---" >&2
  docker logs --tail "$KONG_LOG_TAIL" "$KONG_CONTAINER" 2>&1 | redact_secrets >&2 || true
  return 1
}
# redact_secrets: stdin to stdout with the Future AGI and upstream key values replaced (read from the environment)
redact_secrets() {
  python3 -c 'import os, sys
vals = [v for v in (os.environ.get(k, "") for k in ("FI_API_KEY", "FI_SECRET_KEY", "UPSTREAM_API_KEY")) if len(v) >= 4]
for line in sys.stdin:
    for v in vals:
        line = line.replace(v, "<redacted>")
    sys.stdout.write(line)'
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
