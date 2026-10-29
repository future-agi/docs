#!/usr/bin/env bash
# End-to-end run of the watsonx Orchestrate Agentic SDK recipe against a Future AGI you can read back
# (self-hosted).
#
#   PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh [collector|optin|direct|lifecycle|matrix|all]
#
# Everything here is real: the LangGraph agent with ibm-watsonx-orchestrate-sdk tracing, real model
# calls through OPENAI_BASE_URL, the OpenTelemetry Collector (Docker) and Future AGI. Two wire taps
# record what was sent (header names, never values): one between the SDK and the collector, one
# between the collector and Future AGI. Span payloads stay in $OUT, which must not be committed.
#
# Scenarios
#   collector  three runs through the collector with default settings (content off):
#              an answer with a failed tool call, a run whose model call fails, and a Client-mode
#              tracer that sends a watsonx-style bearer token. Hierarchy, wire and privacy checks:
#              a unique marker, the token, the e-mail in it, user/host/home and stack traces must be
#              absent from every stored column and from the collector's output.
#   optin      KEEP_WXO_CONTENT=true: the marker is stored; stack traces, host and keys still are not;
#              the two projects do not share traces or content.
#   direct     no collector: WXO_OTLP_ENDPOINT straight at Future AGI with the standard OTEL_* env
#              variables. Shows what arrives without the collector (not the recommended setup).
#   lifecycle  collector down (the agent still answers), and a 60 s batch delay that only the
#              tracer.shutdown() flush can beat.
#   matrix     the collector scenario with PYTHON_ALT (another SDK version / Python), also in `all`.
#
# Environment (defaults in brackets)
#   FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI keys and base URL (required)
#   OPENAI_API_KEY, OPENAI_BASE_URL          model endpoint (OPENAI_BASE_URL optional)
#   MODEL [gpt-4.1-mini]  PYTHON [python3]  PYTHON_ALT  VERIFY (fi_verify.py, optional)  OUT [./evidence]
#   FI_PROJECT_PREFIX [wxo-adk-e2e]  RUN_ID [MMDD-HHMM; empty = no suffix]
#   COLLECTOR_IMAGE [otel/opentelemetry-collector-contrib:0.162.0]  COLLECTOR_NAME [wxo-adk-e2e-otelcol]
#   ports: COLLECTOR_PORT [14258] TAP_PORT [14259] SDK_TAP_PORT [14260]
#   FI_PG_CONTAINER, FI_CH_CONTAINER   storage containers read by tools/scan_local_stack.py
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
PREFIX="${FI_PROJECT_PREFIX:-wxo-adk-e2e}"
RUN_ID="${RUN_ID-$(date +%m%d-%H%M)}"
BASE="$PREFIX${RUN_ID:+-$RUN_ID}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
export FI_API_KEY FI_SECRET_KEY OPENAI_API_KEY
MODEL="${MODEL:-gpt-4.1-mini}"
IMAGE="${COLLECTOR_IMAGE:-otel/opentelemetry-collector-contrib:0.162.0}"
COLLECTOR_PORT="${COLLECTOR_PORT:-14258}" TAP_PORT="${TAP_PORT:-14259}" SDK_TAP_PORT="${SDK_TAP_PORT:-14260}"
COLLECTOR_NAME="${COLLECTOR_NAME:-wxo-adk-e2e-otelcol}"
mkdir -p "$OUT"
SUMMARY="$OUT/summary-$MODE.txt"
: >"$SUMMARY"
FAILED=0
TAP_PID="" SDK_TAP_PID=""

say() { printf '\n== %s\n' "$*"; }
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
fail() { note "FAIL  $*"; FAILED=1; }
marker() { "$PY" -c 'import secrets; print("wxo" + secrets.token_hex(6))'; }

wait_port() { # port seconds
  local i=0
  until nc -z 127.0.0.1 "$1" 2>/dev/null; do i=$((i + 1)); [ "$i" -gt $(($2 * 4)) ] && return 1; sleep 0.25; done
}

start_tap() { # name   collector -> Future AGI
  TAP_EXPECT_API_KEY="$FI_API_KEY" TAP_EXPECT_SECRET_KEY="$FI_SECRET_KEY" \
    "$PY" "$HERE/tools/wire_tap.py" --listen "$TAP_PORT" --out "$OUT/wire-$1.jsonl" --forward "${FI_BASE_URL%/}" \
    >"$OUT/tap-$1.log" 2>&1 &
  TAP_PID=$!
  wait_port "$TAP_PORT" 10
}
start_sdk_tap() { # name forward-url   SDK -> collector (records what the SDK sends)
  "$PY" "$HERE/tools/wire_tap.py" --listen "$SDK_TAP_PORT" --out "$OUT/wire-sdk-$1.jsonl" --forward "$2" \
    >"$OUT/sdk-tap-$1.log" 2>&1 &
  SDK_TAP_PID=$!
  wait_port "$SDK_TAP_PORT" 10
}
stop_taps() {
  [ -n "$TAP_PID" ] && kill "$TAP_PID" 2>/dev/null || true
  [ -n "$SDK_TAP_PID" ] && kill "$SDK_TAP_PID" 2>/dev/null || true
  TAP_PID="" SDK_TAP_PID=""
  sleep 0.5
}

start_collector() { # project [docker -e args...]
  local project="$1"; shift
  docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true
  docker run -d --name "$COLLECTOR_NAME" --memory 256m -p "127.0.0.1:$COLLECTOR_PORT:4318" \
    -v "$HERE/otelcol.yaml:/etc/otelcol.yaml:ro" \
    -e FI_TRACES_URL="http://host.docker.internal:$TAP_PORT/tracer/v1/traces" -e FI_API_KEY -e FI_SECRET_KEY \
    -e FI_PROJECT_NAME="$project" "$@" "$IMAGE" --config /etc/otelcol.yaml >/dev/null
  local i=0 code
  until code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$COLLECTOR_PORT/v1/traces") && [ "$code" != 000 ]; do
    i=$((i + 1)); [ "$i" -gt 240 ] && { fail "collector not serving after 60 s"; return 1; }; sleep 0.25
  done
}
stop_collector() { # name: save logs, then remove
  docker logs "$COLLECTOR_NAME" >"$OUT/otelcol-$1.log" 2>&1 || true
  docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true
}

run_agent() { # tag expect(ok|fail) python endpoint question [env...]
  local tag="$1" expect="$2" py="$3" endpoint="$4" question="$5"; shift 5
  local rc=0
  env WXO_OTLP_ENDPOINT="$endpoint" MODEL="$MODEL" "$@" "$py" "$HERE/agent.py" "$question" \
    >"$OUT/agent-$tag.out" 2>"$OUT/agent-$tag.log" || rc=$?
  if { [ "$expect" = ok ] && [ "$rc" = 0 ]; } || { [ "$expect" = fail ] && [ "$rc" != 0 ]; }; then
    note "agent $tag: exit $rc (expected $expect)"
  else
    fail "agent $tag: exit $rc, expected $expect (see agent-$tag.log)"
  fi
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
    note "wire PASS  $1 (uncompressed, both key headers, no Authorization, project_name on every resource)"
  else
    fail "wire  $1 (see wire-summary-$1.txt)"
  fi
}
sdk_wire() { # name needle...   what the SDK itself sent: bearer requests and needles in the payload
  "$PY" - "$OUT/wire-sdk-$1.jsonl" "${@:2}" >"$OUT/sdk-wire-$1.txt" <<'EOF'
import json, sys
lines = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
text = json.dumps([r.get("body") for r in lines])
bearer = sum(1 for r in lines if "authorization" in r.get("header_names", []))
keys = sum(1 for r in lines if r.get("has_key_headers"))
found = {n.split("=", 1)[0]: (n.split("=", 1)[-1] in text) for n in sys.argv[2:]}
print(json.dumps({"requests": len(lines), "with_authorization": bearer, "with_fi_key_headers": keys, "needles_in_sdk_payload": found}))
EOF
  note "sdk wire $1: $(cat "$OUT/sdk-wire-$1.txt")"
}
scan() { # label project [scan args...]
  local label="$1" project="$2"; shift 2
  if "$PY" "$HERE/tools/scan_local_stack.py" --project "$project" --json "$OUT/scan-$label.json" "$@" \
    >"$OUT/scan-$label.txt" 2>&1; then
    note "privacy PASS  $label: $(grep -c ': not found' "$OUT/scan-$label.txt") needle(s) not found, $(grep -c ': FOUND' "$OUT/scan-$label.txt") found ($project)"
  else
    fail "privacy $label (see scan-$label.txt)"
  fi
}
make_token() { # marker -> placeholder JWT-shaped watsonx token with an e-mail user id (not a real credential)
  "$PY" - "$1" <<'EOF'
import base64, json, sys
b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
m = sys.argv[1]
print(".".join([b({"alg": "none"}), b({"tenant_id": "tenant-e2e", "idpUniqueId": f"{m}.user@example.com"}), "sig" + m[::-1]]))
EOF
}

cleanup() { stop_taps; docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# --- scenarios ---------------------------------------------------------------------------------

scenario_collector() { # name python
  local name="$1" py="$2" project="$BASE${1#collector}"
  local m user host token
  m="$(marker)"; user="$(id -un)"; host="$(hostname -s)"
  token="$(make_token "$m")"
  echo "$m" >"$OUT/marker-$name.txt"; echo "$token" >"$OUT/token-$name.txt"
  say "collector: $project"
  note "SDK: $("$py" -c 'import importlib.metadata as m; print("ibm-watsonx-orchestrate-sdk", m.version("ibm-watsonx-orchestrate-sdk"), "langgraph", m.version("langgraph"), "langchain-openai", m.version("langchain-openai"))') on $("$py" -c 'import platform; print("Python", platform.python_version())')"
  start_tap "$name"
  start_collector "$project"
  start_sdk_tap "$name" "http://127.0.0.1:$COLLECTOR_PORT"
  local ep="http://127.0.0.1:$SDK_TAP_PORT/v1/traces"
  run_agent "$name-answer" ok "$py" "$ep" "What is the weather in Tokyo, and in Zq${m}ville?"
  run_agent "$name-failure" fail "$py" "$ep" "What is the weather in Paris? Ref ${m}." MODEL=no-such-model
  local rc=0
  env MODEL="$MODEL" "$py" "$HERE/tools/client_mode_run.py" --collector "$ep" --token-file "$OUT/token-$name.txt" \
    "What is the weather in Lagos? Ref ${m}." >"$OUT/agent-$name-client.out" 2>"$OUT/agent-$name-client.log" || rc=$?
  if [ "$rc" = 0 ]; then note "agent $name-client: exit 0 (Client-mode tracer, bearer token)"; else fail "agent $name-client: exit $rc"; fi
  sleep 3
  stop_collector "$name"
  stop_taps
  sdk_wire "$name" "marker=$m" "email=$m.user@example.com"
  # answer: root + 2-3 agent + 2-3 llm + 2 tool; failure: root + agent + llm; client: root + 2 agent + 2 llm + tool
  verify "$project" 14 --expect-type llm --expect-type tool --expect-type agent --expect-type chain
  check "$project" --traces 3 --tool-error --failed-run --content-off
  wire "$name" "$project"
  scan "$name-content-off" "$project" --wire "$OUT/wire-$name.jsonl" --ignore-case \
    --needle "marker=$m" --needle "bearer_token=$token" --needle "email=$m.user@example.com" \
    --needle "user=$user" --needle "host=$host" --needle "home=$HOME" --needle traceback --needle exception.stacktrace \
    --needle "Unknown User" --needle "api_key=$FI_API_KEY" --needle "secret_key=$FI_SECRET_KEY"
}

scenario_optin() {
  local project="$BASE-optin" m user host
  m="$(marker)"; user="$(id -un)"; host="$(hostname -s)"
  echo "$m" >"$OUT/marker-optin.txt"
  say "opt-in (KEEP_WXO_CONTENT=true): $project"
  start_tap optin
  start_collector "$project" -e KEEP_WXO_CONTENT=true
  run_agent optin-answer ok "$PY" "http://127.0.0.1:$COLLECTOR_PORT/v1/traces" "What is the weather in Tokyo, and in Zq${m}ville?"
  sleep 3
  stop_collector optin
  stop_taps
  verify "$project" 6 --expect-type llm --expect-type tool --expect-type agent --expect-type chain
  check "$project" --traces 1 --tool-error
  wire optin "$project"
  scan optin-content "$project" --needle "marker=$m" --expect-found
  scan optin-always "$project" --wire "$OUT/wire-optin.jsonl" --ignore-case \
    --needle "user=$user" --needle "host=$host" --needle "home=$HOME" --needle traceback --needle exception.stacktrace \
    --needle "Unknown User" --needle "api_key=$FI_API_KEY" --needle "secret_key=$FI_SECRET_KEY"
  if [ -f "$OUT/marker-collector.txt" ]; then
    scan isolation-main "$BASE" --needle "optin_marker=$m"
    scan isolation-optin "$project" --needle "main_marker=$(cat "$OUT/marker-collector.txt")"
    if [ -f "$OUT/spans-$BASE.json" ] && [ -f "$OUT/spans-$project.json" ]; then
      local shared
      shared=$("$PY" -c 'import json,sys; a={s["trace_id"] for s in json.load(open(sys.argv[1]))}; b={s["trace_id"] for s in json.load(open(sys.argv[2]))}; print(len(a & b))' \
        "$OUT/spans-$BASE.json" "$OUT/spans-$project.json")
      if [ "$shared" = 0 ]; then note "isolation PASS  no trace id shared by $BASE and $project"; else fail "isolation: $shared shared trace ids"; fi
    fi
  fi
}

scenario_direct() {
  local project="$BASE-direct"
  say "direct (no collector, not recommended): $project"
  start_tap direct
  run_agent direct-answer ok "$PY" "http://127.0.0.1:$TAP_PORT/tracer/v1/traces" "What is the weather in Tokyo, and in Atlantis?" \
    OTEL_EXPORTER_OTLP_TRACES_HEADERS="X-Api-Key=$FI_API_KEY,X-Secret-Key=$FI_SECRET_KEY" \
    OTEL_RESOURCE_ATTRIBUTES="project_name=$project,project_type=observe"
  sleep 2
  stop_taps
  verify "$project" 6
  if [ -f "$OUT/spans-$project.json" ]; then
    note "direct: $("$PY" -c 'import json,sys,collections; s=json.load(open(sys.argv[1])); print("observation types", dict(collections.Counter(x["observation_type"] for x in s)), "| spans with provider:", sum(1 for x in s if x["provider"]), "| user.id on", sum(1 for x in s if "user.id" in (x["attrs_string"] or {})), "spans")' "$OUT/spans-$project.json")"
  fi
  "$PY" "$HERE/tools/scan_local_stack.py" --project "$project" --wire "$OUT/wire-direct.jsonl" \
    --needle exception.stacktrace --needle "home=$HOME" --needle "Unknown User" --needle "error_text=no weather station for Atlantis" \
    --expect-found --json "$OUT/scan-direct.json" >"$OUT/scan-direct.txt" 2>&1 || true
  note "direct: sent or stored without a collector -> $(grep -E '^  ' "$OUT/scan-direct.txt" | tr -s ' ' | tr '\n' ';')"
}

scenario_lifecycle() {
  local project="$BASE-lifecycle"
  say "lifecycle: nothing listens on :$COLLECTOR_PORT"
  local t0 t1
  t0=$(date +%s)
  run_agent refused ok "$PY" "http://127.0.0.1:$COLLECTOR_PORT/v1/traces" "What is the weather in Tokyo?"
  t1=$(date +%s)
  note "collector down: agent answered and exited in $((t1 - t0)) s; export errors logged: $(grep -c -i -E 'failed to export|connection refused|max retries' "$OUT/agent-refused.log" || true)"

  say "lifecycle: 60 s batch delay, flushed by tracer.shutdown() ($project)"
  start_tap lifecycle
  start_collector "$project"
  run_agent flush ok "$PY" "http://127.0.0.1:$COLLECTOR_PORT/v1/traces" "What is the weather in Lagos?" OTEL_BSP_SCHEDULE_DELAY=60000
  sleep 3
  stop_collector lifecycle
  stop_taps
  verify "$project" 4 --expect-type llm --expect-type tool
  check "$project" --traces 1 --content-off
}

case "$MODE" in
  collector) scenario_collector collector "$PY" ;;
  optin) scenario_optin ;;
  direct) scenario_direct ;;
  lifecycle) scenario_lifecycle ;;
  matrix) [ -n "${PYTHON_ALT:-}" ] && scenario_collector collector-alt "$PYTHON_ALT" ;;
  all)
    scenario_collector collector "$PY"
    scenario_optin
    scenario_direct
    scenario_lifecycle
    [ -n "${PYTHON_ALT:-}" ] && scenario_collector collector-alt "$PYTHON_ALT"
    ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac

say "summary ($SUMMARY)"
cat "$SUMMARY"
exit "$FAILED"
