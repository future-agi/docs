#!/usr/bin/env bash
# End-to-end run of the Restate recipe against a Future AGI you can read back (self-hosted).
#
#   PYTHON=.venv/bin/python RESTATE_SERVER=/path/to/restate-server VERIFY=/path/to/fi_verify.py \
#     ./run_e2e.sh [collector|privacy|direct|lifecycle|matrix|all]
#
# Everything here is real: restate-server, the Python restate-sdk service with traceAI, the
# OpenTelemetry Collector (Docker) and Future AGI. The model is whatever OPENAI_BASE_URL serves.
# A wire tap sits between the collector and Future AGI and records what was sent (header names,
# never values; span payloads stay in $OUT, which must not be committed).
#
# Scenarios
#   collector  answer, a retried tool step, a failed model call; hierarchy + replay checks
#   privacy    content off (the five FI_HIDE_* switches + collector defaults): a unique marker must be absent from
#              every stored column and from the wire; then KEEP_RESTATE_DETAILS=true + default
#              traceAI: the marker must be present
#   direct     no collector: OTEL_RESOURCE_ATTRIBUTES on the server, exporters straight to Future AGI
#   lifecycle  exporter refused (handler still answers), service restart, SIGTERM flush
#   matrix     the collector scenario with RESTATE_SERVER_ALT and/or PYTHON_ALT (also part of `all`)
#
# Environment (defaults in brackets)
#   FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI keys and base URL (required)
#   OPENAI_API_KEY, OPENAI_BASE_URL          model endpoint (OPENAI_BASE_URL optional)
#   MODEL [gpt-4.1-mini]  PYTHON [python3]  RESTATE_SERVER (required)  RESTATE_SERVER_ALT, PYTHON_ALT
#   VERIFY      fi_verify.py of the local stack (optional)   OUT [./evidence]
#   FI_PROJECT_PREFIX [restate-e2e]  RUN_ID [MMDD-HHMM; empty = no suffix]
#   COLLECTOR_IMAGE [otel/opentelemetry-collector-contrib:0.162.0]  COLLECTOR_NAME [restate-e2e-otelcol]
#   ports: COLLECTOR_PORT [14254] TAP_PORT [14255] INGRESS_PORT [18252] ADMIN_PORT [19252]
#          FABRIC_PORT [15252] SERVICE_PORT [19852]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
PREFIX="${FI_PROJECT_PREFIX:-restate-e2e}"
RUN_ID="${RUN_ID-$(date +%m%d-%H%M)}"
BASE="$PREFIX${RUN_ID:+-$RUN_ID}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL}"
: "${RESTATE_SERVER:?set RESTATE_SERVER to a restate-server binary}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
MODEL="${MODEL:-gpt-4.1-mini}"
IMAGE="${COLLECTOR_IMAGE:-otel/opentelemetry-collector-contrib:0.162.0}"
COLLECTOR_PORT="${COLLECTOR_PORT:-14254}" TAP_PORT="${TAP_PORT:-14255}"
INGRESS_PORT="${INGRESS_PORT:-18252}" ADMIN_PORT="${ADMIN_PORT:-19252}" FABRIC_PORT="${FABRIC_PORT:-15252}"
SERVICE_PORT="${SERVICE_PORT:-19852}"
COLLECTOR_NAME="${COLLECTOR_NAME:-restate-e2e-otelcol}"
FI_TRACES="${FI_BASE_URL%/}/tracer/v1/traces"
mkdir -p "$OUT"
SUMMARY="$OUT/summary-$MODE.txt"
: >"$SUMMARY"
FAILED=0
SERVER_PID="" SERVICE_PID="" TAP_PID=""

say() { printf '\n== %s\n' "$*"; }
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
fail() { note "FAIL  $*"; FAILED=1; }
marker() { "$PY" -c 'import secrets; print("rst" + secrets.token_hex(6))'; }

wait_port() { # port seconds
  local i=0
  until nc -z 127.0.0.1 "$1" 2>/dev/null; do i=$((i + 1)); [ "$i" -gt $(($2 * 4)) ] && return 1; sleep 0.25; done
}
wait_http() { # url seconds
  local i=0
  until curl -sf -o /dev/null "$1"; do i=$((i + 1)); [ "$i" -gt $(($2 * 4)) ] && return 1; sleep 0.25; done
}

start_tap() { # name [extra args]
  local name="$1"; shift
  TAP_EXPECT_API_KEY="$FI_API_KEY" TAP_EXPECT_SECRET_KEY="$FI_SECRET_KEY" \
    "$PY" "$HERE/tools/wire_tap.py" --listen "$TAP_PORT" --out "$OUT/wire-$name.jsonl" --forward "${FI_BASE_URL%/}" "$@" \
    >"$OUT/tap-$name.log" 2>&1 &
  TAP_PID=$!
  wait_port "$TAP_PORT" 10
}
stop_tap() { [ -n "$TAP_PID" ] && kill "$TAP_PID" 2>/dev/null || true; TAP_PID=""; sleep 0.5; }

start_collector() { # project [docker -e args...]
  local project="$1"; shift
  docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true
  docker run -d --name "$COLLECTOR_NAME" --memory 256m -p "127.0.0.1:$COLLECTOR_PORT:4318" \
    -v "$HERE/otelcol.yaml:/etc/otelcol.yaml:ro" \
    -e FI_TRACES_URL="http://host.docker.internal:$TAP_PORT/tracer/v1/traces" -e FI_PROJECT_NAME="$project" "$@" \
    "$IMAGE" --config /etc/otelcol.yaml >/dev/null
  # A published port accepts connections before the collector serves. Restate drops a batch it
  # cannot deliver, so wait until the receiver answers HTTP (405 to a GET) before starting Restate.
  local i=0 code
  until code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$COLLECTOR_PORT/tracer/v1/traces") && [ "$code" != 000 ]; do
    i=$((i + 1)); [ "$i" -gt 240 ] && { fail "collector not serving after 60 s"; return 1; }; sleep 0.25
  done
}
stop_collector() { # name: save logs, then remove
  docker logs "$COLLECTOR_NAME" >"$OUT/otelcol-$1.log" 2>&1 || true
  docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true
}

start_restate() { # name endpoint [binary] [extra env...]   (configured from restate.toml + env overrides)
  local name="$1" endpoint="$2" bin="${3:-$RESTATE_SERVER}"; shift 3 || shift $#
  local data="$OUT/restate-data-$name"
  rm -rf "$data"
  env RESTATE_LISTEN_MODE=tcp RESTATE_BIND_IP=127.0.0.1 RESTATE_BIND_PORT="$FABRIC_PORT" \
    RESTATE_ADMIN__BIND_PORT="$ADMIN_PORT" RESTATE_INGRESS__BIND_PORT="$INGRESS_PORT" \
    RESTATE_TRACING_ENDPOINT="$endpoint" \
    RESTATE_TRACING_HEADERS="{X-Api-Key=\"$FI_API_KEY\", X-Secret-Key=\"$FI_SECRET_KEY\"}" \
    "$@" "$bin" --config-file "$HERE/restate.toml" --base-dir "$data" >"$OUT/restate-$name.log" 2>&1 &
  SERVER_PID=$!
  wait_http "http://127.0.0.1:$ADMIN_PORT/health" 60
  note "restate-server $("$bin" --version 2>/dev/null | head -1)  ($name)"
}
stop_restate() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null && wait "$SERVER_PID" 2>/dev/null || true; SERVER_PID=""; }

start_service() { # name project fi_base_url [python] [extra env...]
  local name="$1" project="$2" base="$3" py="${4:-$PY}"; shift 4 || shift $#
  env FI_BASE_URL="$base" FI_PROJECT_NAME="$project" SERVICE_PORT="$SERVICE_PORT" MODEL="$MODEL" "$@" \
    "$py" "$HERE/agent_service.py" >"$OUT/service-$name.log" 2>&1 &
  SERVICE_PID=$!
  wait_port "$SERVICE_PORT" 30
}
stop_service() { # [signal]
  [ -n "$SERVICE_PID" ] || return 0
  kill "-${1:-TERM}" "$SERVICE_PID" 2>/dev/null || true
  wait "$SERVICE_PID" 2>/dev/null || true
  SERVICE_PID=""
}

register() {
  curl -sf -X POST "http://127.0.0.1:$ADMIN_PORT/deployments" -H 'content-type: application/json' \
    -d "{\"uri\":\"http://127.0.0.1:$SERVICE_PORT\"}" >"$OUT/register.json"
}
invoke() { # tag key json -> prints http code; body saved to $OUT/resp-<tag>.json
  curl -s -o "$OUT/resp-$1.json" -w '%{http_code}' --max-time 180 -X POST \
    "http://127.0.0.1:$INGRESS_PORT/WeatherAgent/$2/ask" -H 'content-type: application/json' -d "$3"
}
expect_code() { # tag got want
  if [ "$2" = "$3" ]; then note "invoke $1: HTTP $2 (expected)"; else fail "invoke $1: HTTP $2, expected $3"; fi
}

verify() { # project min-spans [fi_verify args...]
  local project="$1" min="$2"; shift 2
  if [ -z "${VERIFY:-}" ]; then note "fi_verify skipped (VERIFY not set)  $project"; return; fi
  "$PY" "$VERIFY" --project "$project" --wait 120 --min-spans "$min" --json "$OUT/spans-$project.json" "$@" \
    >"$OUT/verify-$project.txt" 2>&1 || true
  if grep -q '^PASS' "$OUT/verify-$project.txt"; then note "fi_verify PASS  $project"; else fail "fi_verify  $project"; fi
}
check() { # project [check_trace args...]
  local project="$1"; shift
  [ -f "$OUT/spans-$project.json" ] || return 0
  if "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-$project.json" "$@" >"$OUT/check-$project.txt" 2>&1; then
    note "check_trace PASS  $project"
  else
    fail "check_trace  $project (see check-$project.txt)"
  fi
}
wire() { # name project
  if "$PY" "$HERE/tools/wire_summary.py" "$OUT/wire-$1.jsonl" --project "$2" >"$OUT/wire-summary-$1.txt" 2>&1; then
    note "wire PASS  $1 (uncompressed, both key headers, project_name on every resource)"
  else
    fail "wire  $1 (see wire-summary-$1.txt)"
  fi
}

cleanup() { stop_service KILL; stop_restate; stop_tap; docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# --- scenarios ---------------------------------------------------------------------------------

scenario_collector() { # name restate-binary python
  local name="$1" bin="$2" py="$3" project="$BASE${1#collector}"
  [ "$name" = collector ] && project="$BASE"
  say "collector: $project"
  start_tap "$name"
  start_collector "$project"
  start_restate "$name" "otlp+http://127.0.0.1:$COLLECTOR_PORT/tracer/v1/traces" "$bin"
  start_service "$name" "$project" "http://127.0.0.1:$COLLECTOR_PORT" "$py"
  register
  expect_code answer "$(invoke "$name-answer" user-1 '{"question":"What is the weather in Lisbon today?"}')" 200
  expect_code retry "$(invoke "$name-retry" user-2 '{"question":"What is the weather in Oslo?","flaky":true}')" 200
  expect_code failure "$(invoke "$name-failure" user-3 '{"question":"Weather in Rome?","model":"no-such-model"}')" 500
  sleep 8
  stop_service TERM
  stop_restate
  sleep 3
  stop_collector "$name"
  stop_tap
  # answer 4 server + 3 app, retry 5 + 4, failure 5 + 2
  verify "$project" 23 --expect-type llm --expect-type tool
  check "$project" --invocations 3 --model-steps 2
  wire "$name" "$project"
}

scenario_privacy() {
  local off="$BASE-content-off" on="$BASE-details-on" m1 m2
  m1="$(marker)"; m2="$(marker)"
  local user host
  user="$(id -un)"; host="$(hostname -s)"
  echo "$m1" >"$OUT/marker-off.txt"; echo "$m2" >"$OUT/marker-on.txt"

  say "privacy, content off: $off"
  start_tap content-off
  start_collector "$off"
  start_restate content-off "otlp+http://127.0.0.1:$COLLECTOR_PORT/tracer/v1/traces"
  start_service content-off "$off" "http://127.0.0.1:$COLLECTOR_PORT" "$PY" \
    FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_INPUT_MESSAGES=true FI_HIDE_OUTPUT_MESSAGES=true \
    FI_HIDE_LLM_INVOCATION_PARAMETERS=true
  register
  expect_code off-answer "$(invoke off-answer "$m1@example.com" "{\"question\":\"What is the weather in Zq${m1}ville today?\",\"flaky\":true}")" 200
  expect_code off-failure "$(invoke off-failure "$m1-b@example.com" "{\"question\":\"Weather in Zq${m1}ville?\",\"model\":\"no-such-model-$m1\"}")" 500
  sleep 8; stop_service TERM; stop_restate; sleep 3; stop_collector content-off; stop_tap
  # answer with a retried tool step 5 server + 4 app, failed model call 5 + 2
  verify "$off" 16 --expect-type llm --expect-type tool
  wire content-off "$off"
  if "$PY" "$HERE/tools/scan_local_stack.py" --project "$off" --wire "$OUT/wire-content-off.jsonl" --ignore-case \
    --needle "marker=$m1" --needle "user=$user" --needle "host=$host" --needle "home=$HOME" \
    --needle "service_address=127.0.0.1:$SERVICE_PORT" --needle traceback --needle exception.stacktrace \
    --needle "api_key=$FI_API_KEY" --needle "secret_key=$FI_SECRET_KEY" --needle "@example.com" \
    --json "$OUT/scan-content-off.json" >"$OUT/scan-content-off.txt" 2>&1; then
    note "privacy PASS  content off: marker, user, host, home, service address, stack traces, keys: 0 hits (stored + wire)"
  else
    fail "privacy content off (see scan-content-off.txt)"
  fi

  say "privacy, opt-in: $on"
  start_tap details-on
  start_collector "$on" -e KEEP_RESTATE_DETAILS=true
  start_restate details-on "otlp+http://127.0.0.1:$COLLECTOR_PORT/tracer/v1/traces"
  start_service details-on "$on" "http://127.0.0.1:$COLLECTOR_PORT"
  register
  expect_code on-answer "$(invoke on-answer "$m2@example.com" "{\"question\":\"What is the weather in Zq${m2}ville today?\"}")" 200
  expect_code on-failure "$(invoke on-failure "$m2-b@example.com" "{\"question\":\"Weather in Zq${m2}ville?\",\"model\":\"no-such-model-$m2\"}")" 500
  sleep 8; stop_service TERM; stop_restate; sleep 3; stop_collector details-on; stop_tap
  verify "$on" 14 --expect-type llm --expect-type tool
  if "$PY" "$HERE/tools/scan_local_stack.py" --project "$on" --needle "marker=$m2" --expect-found \
    --json "$OUT/scan-details-on.json" >"$OUT/scan-details-on.txt" 2>&1; then
    note "privacy PASS  opt-in: marker stored (prompt, key, error text)"
  else
    fail "privacy opt-in: marker not stored (see scan-details-on.txt)"
  fi
  if "$PY" "$HERE/tools/scan_local_stack.py" --project "$on" --wire "$OUT/wire-details-on.jsonl" --ignore-case \
    --needle "user=$user" --needle "host=$host" --needle "home=$HOME" --needle "service_address=127.0.0.1:$SERVICE_PORT" \
    --needle exception.stacktrace --needle "api_key=$FI_API_KEY" --needle "secret_key=$FI_SECRET_KEY" \
    --json "$OUT/scan-details-on-always.json" >"$OUT/scan-details-on-always.txt" 2>&1; then
    note "privacy PASS  opt-in still removes user, host, home, service address, stack traces, keys"
  else
    fail "privacy opt-in always-removed fields (see scan-details-on-always.txt)"
  fi
}

scenario_direct() { # name restate-binary
  local name="$1" bin="$2" project="$BASE-$1"
  say "direct (no collector): $project"
  start_tap "$name"
  start_restate "$name" "otlp+http://127.0.0.1:$TAP_PORT/tracer/v1/traces" "$bin" \
    OTEL_RESOURCE_ATTRIBUTES="project_name=$project,project_type=observe"
  start_service "$name" "$project" "http://127.0.0.1:$TAP_PORT"
  register
  expect_code "$name-answer" "$(invoke "$name-answer" user-1 '{"question":"What is the weather in Lisbon today?"}')" 200
  expect_code "$name-retry" "$(invoke "$name-retry" user-2 '{"question":"What is the weather in Oslo?","flaky":true}')" 200
  sleep 8; stop_service TERM; stop_restate; sleep 2; stop_tap
  verify "$project" 16 --expect-type llm --expect-type tool
  check "$project" --invocations 2 --model-steps 2
  wire "$name" "$project"
}

scenario_lifecycle() {
  local project="$BASE-lifecycle" refused="$BASE-refused"
  say "lifecycle: exporter refused ($refused, nothing listens on :$COLLECTOR_PORT)"
  start_restate refused "otlp+http://127.0.0.1:$COLLECTOR_PORT/tracer/v1/traces"
  start_service refused "$refused" "http://127.0.0.1:$COLLECTOR_PORT"
  register
  expect_code refused "$(invoke refused user-1 '{"question":"What is the weather in Lisbon today?"}')" 200
  sleep 7; stop_service TERM; stop_restate
  local warn_s warn_r
  warn_s=$(grep -c -i -E 'failed to export|connection refused|max retries' "$OUT/service-refused.log" || true)
  warn_r=$(grep -c -i -E 'opentelemetry|export|trace' "$OUT/restate-refused.log" | head -1 || true)
  note "refused exporter: handler answered; service log export warnings: $warn_s; restate log trace/export lines: $warn_r"

  say "lifecycle: restart + SIGTERM flush ($project)"
  start_tap lifecycle
  start_collector "$project"
  start_restate lifecycle "otlp+http://127.0.0.1:$COLLECTOR_PORT/tracer/v1/traces"
  start_service lifecycle-1 "$project" "http://127.0.0.1:$COLLECTOR_PORT"
  register
  expect_code before-restart "$(invoke before-restart user-1 '{"question":"What is the weather in Lisbon today?"}')" 200
  sleep 7
  stop_service KILL # crash: nothing is flushed on purpose; spans of the first call were exported by now
  start_service lifecycle-2 "$project" "http://127.0.0.1:$COLLECTOR_PORT" "$PY" OTEL_BSP_SCHEDULE_DELAY=60000
  expect_code after-restart "$(invoke after-restart user-2 '{"question":"What is the weather in Oslo?"}')" 200
  # The batch delay is 60 s, so these spans are still buffered: only the SIGTERM flush can send them.
  stop_service TERM
  note "SIGTERM sent right after the answer (batch delay 60 s)"
  sleep 4; stop_restate; sleep 3; stop_collector lifecycle; stop_tap
  verify "$project" 14 --expect-type llm --expect-type tool
  check "$project" --invocations 2 --model-steps 2
  wire lifecycle "$project"
}

case "$MODE" in
  collector) scenario_collector collector "$RESTATE_SERVER" "$PY" ;;
  privacy) scenario_privacy ;;
  direct)
    scenario_direct direct "$RESTATE_SERVER"
    [ -n "${RESTATE_SERVER_ALT:-}" ] && scenario_direct direct-alt "$RESTATE_SERVER_ALT"
    ;;
  lifecycle) scenario_lifecycle ;;
  matrix)
    [ -n "${RESTATE_SERVER_ALT:-}" ] && scenario_collector collector-server-alt "$RESTATE_SERVER_ALT" "$PY"
    [ -n "${PYTHON_ALT:-}" ] && scenario_collector collector-python-alt "$RESTATE_SERVER" "$PYTHON_ALT"
    ;;
  all)
    scenario_collector collector "$RESTATE_SERVER" "$PY"
    scenario_privacy
    scenario_direct direct "$RESTATE_SERVER"
    [ -n "${RESTATE_SERVER_ALT:-}" ] && scenario_direct direct-alt "$RESTATE_SERVER_ALT"
    scenario_lifecycle
    [ -n "${RESTATE_SERVER_ALT:-}" ] && scenario_collector collector-server-alt "$RESTATE_SERVER_ALT" "$PY"
    [ -n "${PYTHON_ALT:-}" ] && scenario_collector collector-python-alt "$RESTATE_SERVER" "$PYTHON_ALT"
    ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac

say "summary ($SUMMARY)"
cat "$SUMMARY"
exit "$FAILED"
