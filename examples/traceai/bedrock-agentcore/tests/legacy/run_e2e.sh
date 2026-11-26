#!/usr/bin/env bash
# End-to-end run of the AgentCore recipe against a Future AGI you can read back (self-hosted).
#
#   PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh [langchain|strands|all]
#   CONTAINER=1 ... ./run_e2e.sh langchain     # same, with the agent inside the runtime-shaped image
#
# What is real: bedrock-agentcore's BedrockAgentCoreApp HTTP server (POST /invocations, GET /ping,
# the session header), the LangChain + traceAI and Strands agents, an OpenAI-compatible model, the
# OpenTelemetry exporters and Future AGI. What is not: AWS. No AgentCore Runtime is created and
# InvokeAgentRuntime is not called; tools/invoke.py sends the same HTTP request the runtime
# forwards to the container (body, X-Amzn-Bedrock-AgentCore-Runtime-Session-Id, traceparent).
#
# Per path and project:  happy (3 invocations, one session, traceparent on the first and
#   JOIN_CALLER_TRACE=true, the "caller is traced too" case)
#   failure (the model rejects the request -> AgentCore answers 500, ERROR spans, flushed; a
#   traceparent is sent without JOIN_CALLER_TRACE, so the root starts its own, listed trace;
#   every stored column scanned: no Traceback, local path, username, hostname or API key even
#   with the path's default content setting)
#   privacy (unique marker in the prompt and the tool arguments; every stored column scanned,
#   for the marker and for the local username, hostname, home path and "Traceback")
#   failure-off (the failure again with content off: every ERROR span keeps the exception type
#   name only; nothing of the marker, the error text or a stack trace is stored)
#   deadend (collector unreachable: the invocations still return)
#
# Needs: FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL (Future AGI origin, e.g. http://localhost:8000),
# OPENAI_API_KEY + OPENAI_BASE_URL + AGENT_MODEL (any OpenAI-compatible endpoint), VERIFY
# (fi_verify.py of the self-hosted stack), docker access to the stack's ClickHouse/Postgres for
# tools/scan_columns.py. CONTAINER=1 also needs docker and IN_CONTAINER_FI_BASE_URL /
# IN_CONTAINER_OPENAI_BASE_URL (how the container reaches the same services).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
BASE="${FI_PROJECT_PREFIX:-agentcore-recipe}-${RUN_ID:-$(date +%m%d-%H%M)}"
PORT="${PORT:-18080}"
MODEL="${AGENT_MODEL:-gpt-4o-mini}"
IMAGE="${IMAGE:-agentcore-recipe-runtime:local}"
CNAME="${CONTAINER_NAME:-agentcore-recipe-agent}"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}" "${OPENAI_API_KEY:?}" "${OPENAI_BASE_URL:?}" "${VERIFY:?set VERIFY to fi_verify.py}"
TRACEPARENT="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
mkdir -p "$OUT"; SUMMARY="$OUT/summary-$MODE${CONTAINER:+-container}.txt"; : >"$SUMMARY"; FAILED=0
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
fail() { note "FAIL  $*"; FAILED=1; }
ok() { note "ok    $*"; }

# start_agent PATH PROJECT LOG [VAR=VALUE ...]  -> the app in the background, waits for GET /ping
start_agent() {
  local path="$1" project="$2" log="$3"; shift 3
  local fi_url="$FI_BASE_URL" model_url="$OPENAI_BASE_URL"
  if [ -n "${CONTAINER:-}" ]; then fi_url="${IN_CONTAINER_FI_BASE_URL:?}"; model_url="${IN_CONTAINER_OPENAI_BASE_URL:?}"; fi
  local -a envs=(DISABLE_ADOT_OBSERVABILITY=true AGENT_MODEL="$MODEL" OPENAI_BASE_URL="$model_url")
  if [ "$path" = langchain ]; then
    envs+=(FI_BASE_URL="$fi_url" FI_PROJECT_NAME="$project")
  else
    envs+=(OTEL_EXPORTER_OTLP_ENDPOINT="$fi_url" OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
           OTEL_RESOURCE_ATTRIBUTES="project_name=$project,project_type=observe"
           OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_latest_experimental,gen_ai_span_attributes_only,gen_ai_unredacted_attributes=")
  fi
  envs+=("$@")
  # Secrets stay out of argument lists: OTEL_EXPORTER_OTLP_HEADERS is built in the environment.
  export OTEL_EXPORTER_OTLP_HEADERS="X-Api-Key=$FI_API_KEY,X-Secret-Key=$FI_SECRET_KEY"
  if [ -n "${CONTAINER:-}" ]; then
    local -a dargs=(-e FI_API_KEY -e FI_SECRET_KEY -e OPENAI_API_KEY)
    [ "$path" = strands ] && dargs+=(-e OTEL_EXPORTER_OTLP_HEADERS)
    local kv; for kv in "${envs[@]}"; do dargs+=(-e "$kv"); done
    docker rm -f "$CNAME" >/dev/null 2>&1
    docker run -d --name "$CNAME" --memory 512m --add-host=host.docker.internal:host-gateway \
      -p "127.0.0.1:$PORT:8080" "${dargs[@]}" "$IMAGE" python -m "agent_$path" >/dev/null || return 1
    ( docker logs -f "$CNAME" >"$log" 2>&1 & )
  else
    if [ "$path" = langchain ]; then unset OTEL_EXPORTER_OTLP_HEADERS; fi
    env PORT="$PORT" "${envs[@]}" "$PY" "$HERE/agent_$path.py" >"$log" 2>&1 &
    AGENT_PID=$!
  fi
  local i; for i in $(seq 1 90); do curl -sf "http://127.0.0.1:$PORT/ping" >/dev/null && return 0; sleep 1; done
  return 1
}
stop_agent() {
  if [ -n "${CONTAINER:-}" ]; then docker stop -t 10 "$CNAME" >/dev/null 2>&1; docker rm -f "$CNAME" >/dev/null 2>&1
  else kill "${AGENT_PID:-0}" 2>/dev/null; wait "${AGENT_PID:-0}" 2>/dev/null; fi
}
verify() { # project min-spans json   (min-spans: ingestion is asynchronous, so wait for all of them)
  local i
  for i in 1 2 3 4; do
    "$PY" "$VERIFY" --project "$1" --wait 90 --min-spans "$2" --json "$3" >"$3.txt" 2>&1
    grep -q "clickhouse error" "$3.txt" || break
    sleep 30
  done
  grep -E "^(traces=|PASS|FAIL)" "$3.txt" | tr '\n' ' ' | tee -a "$SUMMARY"; echo | tee -a "$SUMMARY"
  grep -q '^PASS' "$3.txt"
}
scan() { # project marker tag -> counts in $OUT/scan-<tag>.txt
  "$PY" "$HERE/tools/scan_columns.py" "$1" "marker=$2" "username=$(id -un)" "hostname=$(hostname -s)" \
    "home=$HOME" "traceback=Traceback" "apikey=$FI_API_KEY" | tee "$OUT/scan-$3.txt" | tee -a "$SUMMARY"
  grep -q "^project rows: [1-9]" "$OUT/scan-$3.txt" || fail "$3: no stored rows to scan (a scan of nothing proves nothing)"
}
count() { grep -E "^$1:" "$OUT/scan-$2.txt" | sed 's/.*= //'; }

path_suite() {
  local path="$1" tag="$2${CONTAINER:+-ct}" p m log k bad
  m="mk$("$PY" -c 'import secrets;print(secrets.token_hex(6))')"
  note; note "=== $path${CONTAINER:+ (container $IMAGE)} ==="
  # happy: J2 + J3 + J6
  p="$BASE-$tag-happy"; log="$OUT/run-$tag-happy.txt"
  start_agent "$path" "$p" "$log.server" JOIN_CALLER_TRACE=true || fail "$path happy: server did not start"
  "$PY" "$HERE/tools/invoke.py" "http://127.0.0.1:$PORT" "e2e-session-$tag-0001" \
    "What is the status of order A-100?" "And order A-200?" "Is order A-100 still shipped?" \
    --traceparent "$TRACEPARENT" | tee "$log"
  stop_agent
  [ "$(grep -c '^status=200' "$log")" = 3 ] && ok "$path happy: 3 invocations returned 200" || fail "$path happy: invocations"
  verify "$p" "$([ "$path" = langchain ] && echo 24 || echo 21)" "$OUT/spans-$tag-happy.json" && "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-$tag-happy.json" happy | tee -a "$SUMMARY" \
    || fail "$path happy: trace shape"
  # failure: J4 (the model endpoint rejects the model id)
  p="$BASE-$tag-failure"; log="$OUT/run-$tag-failure.txt"
  start_agent "$path" "$p" "$log.server" AGENT_MODEL=th8226-no-such-model || fail "$path failure: server did not start"
  "$PY" "$HERE/tools/invoke.py" "http://127.0.0.1:$PORT" "e2e-session-$tag-0002" "What is the status of order $m?" \
    --traceparent "$TRACEPARENT" | tee "$log"
  stop_agent
  grep -q '^status=500' "$log" && ok "$path failure: AgentCore answered 500" || fail "$path failure: expected 500"
  verify "$p" 4 "$OUT/spans-$tag-failure.json" && "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-$tag-failure.json" failure | tee -a "$SUMMARY" \
    || fail "$path failure: trace shape"
  # stack traces and local details are never stored, whatever the content setting
  scan "$p" "$m" "$tag-failure"
  bad=0; for k in username hostname home traceback apikey; do [ "$(count $k "$tag-failure")" = 0 ] || bad=1; done
  [ $bad = 0 ] && ok "$path failure, default content setting: no Traceback, local path, username, hostname or API key stored" \
    || fail "$path failure: stack trace, path, username, hostname or key stored (see scan-$tag-failure.txt)"
  [ -n "${CONTAINER:-}" ] && return 0
  # privacy: marker in the prompt and in the tool arguments/result
  local -a off on
  if [ "$path" = langchain ]; then  # traceAI TraceConfig: content on by default, FI_HIDE_* hides it
    off=(FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true); on=()
  else                              # recipe default: Strands redaction on; opt-in = no redaction token
    off=(); on=(OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental,gen_ai_span_attributes_only)
  fi
  p="$BASE-$tag-priv-off"; log="$OUT/run-$tag-priv-off.txt"
  start_agent "$path" "$p" "$log.server" "${off[@]}" || fail "$path privacy off: server"
  "$PY" "$HERE/tools/invoke.py" "http://127.0.0.1:$PORT" "e2e-session-$tag-0003" "What is the status of order $m?" | tee "$log"
  stop_agent
  verify "$p" 7 "$OUT/spans-$tag-priv-off.json" || fail "$path privacy off: fi_verify"
  scan "$p" "$m" "$tag-priv-off"
  bad=0; for k in marker username hostname home traceback apikey; do [ "$(count $k "$tag-priv-off")" = 0 ] || bad=1; done
  [ $bad = 0 ] && ok "$path content off: marker, username, hostname, home path, Traceback, API key absent from every stored column" \
    || fail "$path content off: something is stored (see scan-$tag-priv-off.txt)"
  p="$BASE-$tag-priv-on"; log="$OUT/run-$tag-priv-on.txt"
  start_agent "$path" "$p" "$log.server" "${on[@]}" || fail "$path privacy on: server"
  "$PY" "$HERE/tools/invoke.py" "http://127.0.0.1:$PORT" "e2e-session-$tag-0004" "What is the status of order $m?" | tee "$log"
  stop_agent
  verify "$p" 7 "$OUT/spans-$tag-priv-on.json" || fail "$path privacy on: fi_verify"
  scan "$p" "$m" "$tag-priv-on"
  [ "$(count marker "$tag-priv-on")" != 0 ] && ok "$path content on: marker stored" || fail "$path content on: marker not stored"
  bad=0; for k in username hostname home traceback apikey; do [ "$(count $k "$tag-priv-on")" = 0 ] || bad=1; done
  [ $bad = 0 ] && ok "$path content on: still no username, hostname, home path, Traceback, API key" || fail "$path content on: user/host/path/stack/key stored"
  # failure with content off: no error text, no stack trace
  p="$BASE-$tag-failure-off"; log="$OUT/run-$tag-failure-off.txt"
  start_agent "$path" "$p" "$log.server" AGENT_MODEL=th8226-no-such-model "${off[@]}" || fail "$path failure off: server"
  "$PY" "$HERE/tools/invoke.py" "http://127.0.0.1:$PORT" "e2e-session-$tag-0005" "What is the status of order $m?" | tee "$log"
  stop_agent
  verify "$p" 4 "$OUT/spans-$tag-failure-off.json" && "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-$tag-failure-off.json" failure-off | tee -a "$SUMMARY" \
    || fail "$path failure off: fi_verify or error spans not reduced to the exception type"
  scan "$p" "$m" "$tag-failure-off"
  bad=0; for k in marker username hostname home traceback apikey; do [ "$(count $k "$tag-failure-off")" = 0 ] || bad=1; done
  [ $bad = 0 ] && ok "$path failure, content off: no marker, error text path, username, hostname or Traceback stored" \
    || fail "$path failure, content off: something is stored (see scan-$tag-failure-off.txt)"
  # dead end: collector unreachable
  local t0
  start_agent "$path" "$BASE-$tag-dead" "$OUT/run-$tag-dead.txt.server" \
    FI_BASE_URL=http://127.0.0.1:9 OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:9 || fail "$path dead end: server"
  t0=$SECONDS
  "$PY" "$HERE/tools/invoke.py" "http://127.0.0.1:$PORT" "e2e-session-$tag-0006" "What is the status of order A-100?" "And order A-200?" | tee "$OUT/run-$tag-dead.txt"
  stop_agent
  [ "$(grep -c '^status=200' "$OUT/run-$tag-dead.txt")" = 2 ] && ok "$path unreachable collector: 2 invocations returned 200 in $((SECONDS - t0))s" \
    || fail "$path unreachable collector: invocations failed"
}

if [ -n "${CONTAINER:-}" ]; then
  docker build -q -t "$IMAGE" "$HERE" >/dev/null || { fail "docker build"; exit 1; }
fi
if [ "$MODE" = langchain ] || [ "$MODE" = all ]; then path_suite langchain lc; fi
if [ "$MODE" = strands ] || [ "$MODE" = all ]; then path_suite strands st; fi
note; [ "$FAILED" = 0 ] && note "E2E PASS" || note "E2E FAIL"
exit "$FAILED"
