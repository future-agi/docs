#!/usr/bin/env bash
# End-to-end run of the TrueFoundry recipes against a self-hosted Future AGI.
#
#   source <env with FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL, CLIPROXY_API_KEY, CLIPROXY_OPENAI_BASE_URL>
#   PYTHON=/path/to/venv/bin/python ./run_e2e.sh [client|native|collector|all]
#
# What is real and what is not:
#   real     traceai-openai + openai (client), the Future AGI collector and storage, the OpenTelemetry
#            Collector container (collector mode)
#   STAND-IN the TrueFoundry gateway. standin_gateway.py serves the documented gateway surface and
#            forwards to an OpenAI-compatible upstream. The native-export batches are SYNTHETIC,
#            built from TrueFoundry's attribute docs. No TrueFoundry code runs.
#
# Needs: Docker (collector mode, and the scan step), `pip install -r requirements.txt`.
# Environment (defaults in brackets):
#   PYTHON [python3]  OUT [./evidence]  FI_PROJECT_PREFIX [th8103-rest-truefoundry]  RUN_ID [MMDD-HHMM, fresh projects per run]
#   STANDIN_UPSTREAM_BASE_URL [$CLIPROXY_OPENAI_BASE_URL]  STANDIN_UPSTREAM_API_KEY [$CLIPROXY_API_KEY]
#   STANDIN_MODEL [gpt-6-luna]   upstream model behind the stand-in's openai-main/<model>
#   VERIFY    path to fi_verify.py of the local stack (optional; skipped when unset)
#   SKIP_SCAN=1  skip the stored-rows scan (it reads the local stack's Docker containers)
# Content is never printed; evidence files can contain prompts and stay out of git.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
PREFIX="${FI_PROJECT_PREFIX:-th8103-rest-truefoundry}"
# Every run gets fresh projects so the span counts below are exact. RUN_ID= (empty) reuses fixed names.
RUN_ID="${RUN_ID-$(date +%m%d-%H%M)}"
P="$PREFIX${RUN_ID:+-$RUN_ID}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL}"
UPSTREAM="${STANDIN_UPSTREAM_BASE_URL:-${CLIPROXY_OPENAI_BASE_URL:-}}"
UPSTREAM_KEY="${STANDIN_UPSTREAM_API_KEY:-${CLIPROXY_API_KEY:-}}"
UPSTREAM_MODEL="${STANDIN_MODEL:-gpt-6-luna}"
STANDIN_PORT=18304
TAP_PORT=18305
COLLECTOR_NAME="th8103-rest-truefoundry-otelcol"
mkdir -p "$OUT"
SUMMARY="$OUT/summary-$MODE.txt"
: > "$SUMMARY"
PIDS=()
FAILED=0

say() { printf '\n== %s\n' "$*"; }
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
uid() { "$PY" -c 'import uuid; print(uuid.uuid4().hex[:12])'; }
cleanup() {
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null || true; done
  docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

verify() { # project min-spans [extra fi_verify args...]
  local project="$1" min="$2"; shift 2
  if [ -z "${VERIFY:-}" ]; then note "fi_verify skipped (VERIFY not set)  $project"; return; fi
  "$PY" "$VERIFY" --project "$project" --wait 90 --min-spans "$min" --json "$OUT/spans-$project.json" "$@" \
    >"$OUT/verify-$project.txt" 2>&1 || true
  sed -n '1,14p' "$OUT/verify-$project.txt"
  if grep -q '^PASS' "$OUT/verify-$project.txt"; then note "fi_verify PASS  $project"; else note "fi_verify FAIL  $project"; FAILED=1; fi
}

scan() { # project wire-file expect(found|absent) needle...
  local project="$1" wire="$2" expect="$3"; shift 3
  if [ "${SKIP_SCAN:-0}" = 1 ]; then note "scan skipped  $project"; return; fi
  local args=(--project "$project" --ignore-case --json "$OUT/scan-$project.json")
  [ -n "$wire" ] && args+=(--wire "$wire")
  [ "$expect" = found ] && args+=(--expect-found)
  for n in "$@"; do args+=(--needle "$n"); done
  if "$PY" -I "$HERE/tools/scan_local_stack.py" "${args[@]}" | tee "$OUT/scanlog-$project.txt"; then
    note "scan expected-$expect OK  $project"
  else
    note "scan expected-$expect NOT MET  $project"
    return 1
  fi
}

start_tap() { # name forward-url
  rm -f "$OUT/wire-$1.jsonl"
  "$PY" "$HERE/tools/wire_tap.py" --listen "$TAP_PORT" --forward "$2" --out "$OUT/wire-$1.jsonl" >"$OUT/tap-$1.log" 2>&1 &
  TAP_PID=$!; PIDS+=("$TAP_PID"); sleep 1
}
stop_tap() { kill "$TAP_PID" 2>/dev/null || true; wait "$TAP_PID" 2>/dev/null || true; }

PRIVACY_NEEDLES=(
  "username=$(id -un)" "hostname=$(hostname)" "shorthost=$(hostname -s)"
  "home=$HOME" "cwd=$PWD" "traceback=Traceback" "stacktrace=exception.stacktrace"
)

# ---------------------------------------------------------------- client path (J1)
client_run() { # name model hide(0|1) prompt
  local name="$1" model="$2" hide="$3" prompt="$4"
  start_tap "client-$name" "$FI_BASE_URL"
  local project="$P-$name"
  local env=(FI_BASE_URL="http://127.0.0.1:$TAP_PORT" TFY_BASE_URL="http://127.0.0.1:$STANDIN_PORT"
             TFY_API_KEY=tfy-standin-token TFY_MODEL="$model" FI_PROJECT_NAME="$project")
  if [ "$hide" = 1 ]; then
    env+=(FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_INPUT_MESSAGES=true FI_HIDE_OUTPUT_MESSAGES=true FI_HIDE_LLM_INVOCATION_PARAMETERS=true)
  fi
  env "${env[@]}" "$PY" "$HERE/client_example.py" "$prompt" 2>&1 | grep -v 'ai-evaluation is not installed' | sed 's/^/  client: /' || true
  stop_tap
}

run_client() {
  say "client path: traceai-openai -> STAND-IN TrueFoundry gateway -> local Future AGI"
  [ -n "$UPSTREAM" ] || { echo "set STANDIN_UPSTREAM_BASE_URL (an OpenAI-compatible endpoint)"; exit 2; }
  STANDIN_UPSTREAM_BASE_URL="$UPSTREAM" STANDIN_UPSTREAM_API_KEY="$UPSTREAM_KEY" STANDIN_PORT=$STANDIN_PORT \
    STANDIN_MODELS="openai-main/$UPSTREAM_MODEL" "$PY" "$HERE/standin_gateway.py" >"$OUT/standin.log" 2>&1 &
  PIDS+=("$!"); sleep 1
  local model="openai-main/$UPSTREAM_MODEL"
  "$PY" -c "import traceai_openai, openai; from importlib.metadata import version as v; print('versions: traceai-openai', v('traceai-openai'), 'openai', v('openai'), 'fi-instrumentation-otel', v('fi-instrumentation-otel'))" | tee -a "$SUMMARY"

  say "C1 success, with a tool call"
  client_run client "$model" 0 "What is the shipping status of order A-1042? Use the tool."
  verify "$P-client" 4 --expect-type agent --expect-type llm --expect-type tool

  say "C2 failure: a model the caller may not use (403 from the gateway)"
  client_run fail "openai-main/not-a-model" 0 "What is the shipping status of order A-1042? Use the tool."
  verify "$P-fail" 2 --expect-type llm
  grep -q 'status=ERROR' "$OUT/verify-$P-fail.txt" 2>/dev/null && note "ERROR status present  $P-fail" || { note "ERROR status MISSING  $P-fail"; FAILED=1; }

  say "C3 content off (documented FI_HIDE_* switches), unique markers in prompt, tool arguments and results"
  local m1="TFYA$(uid)" m2="TFYB$(uid)"
  client_run hidden "$model" 1 "Order $m1 has this customer note: $m2. What is its shipping status? Use the tool."
  verify "$P-hidden" 4 --expect-type llm --expect-type tool
  scan "$P-hidden" "$OUT/wire-client-hidden.jsonl" absent "marker_prompt=$m1" "marker_note=$m2" "${PRIVACY_NEEDLES[@]}" || FAILED=1

  say "C4 content on (default capture): the marker must now be stored"
  local m3="TFYC$(uid)"
  client_run optin "$model" 0 "Order $m3 shipping status? Use the tool."
  verify "$P-optin" 4 --expect-type llm --expect-type tool
  scan "$P-optin" "$OUT/wire-client-optin.jsonl" found "marker=$m3" || FAILED=1

  say "C5 failure with content off: records what a failed call still exports (a known limitation, not a pass/fail gate)"
  local m4="TFYD$(uid)"
  client_run failhidden "openai-main/not-a-model" 1 "Order $m4 status? Use the tool."
  verify "$P-failhidden" 2 --expect-type llm
  scan "$P-failhidden" "$OUT/wire-client-failhidden.jsonl" absent "marker=$m4" "${PRIVACY_NEEDLES[@]}" "errtext=not authorized" \
    || note "(expected) the failure path exports error text and, on the wire, a stack trace: see README, Limitations"
}

# ---------------------------------------------------------------- native export, direct (J2)
post() { # args for post_batch.py; output is appended to the summary
  "$PY" "$HERE/native/post_batch.py" "$@" | tee -a "$SUMMARY"
}

run_native() {
  say "native export, SYNTHETIC TrueFoundry-shaped batches posted straight to the Future AGI collector"
  local url="$FI_BASE_URL/v1/traces" p="$P-native"
  note "D1 no project_name"
  post --url "$url" --marker TFYN1 || note "(expected) rejected: the collector needs resource attribute project_name"

  say "D2 documented setup: two header pairs plus Additional Resource Attributes project_name/project_type"
  local d2="TFYE$(uid)"
  start_tap native-direct "$FI_BASE_URL"
  post --url "http://127.0.0.1:$TAP_PORT/v1/traces" --marker "$d2" --resource "project_name=$p" --resource project_type=observe
  stop_tap; sleep 4
  verify "$p" 2 --expect-type llm
  scan "$p" "$OUT/wire-native-direct.jsonl" found "marker=$d2" || FAILED=1

  say "D3 gateway without ENABLE_GEN_AI_OTEL_ATTRIBUTES: tfy.* attributes only"
  post --url "$url" --marker "TFYF$(uid)" --genai off --resource "project_name=$p-noflag" --resource project_type=observe
  sleep 4; verify "$p-noflag" 2

  say "D4 failed request (OTLP status ERROR is assumed, see tfy_batch.py)"
  post --url "$url" --marker "TFYG$(uid)" --failure --resource "project_name=$p-fail" --resource project_type=observe
  sleep 4; verify "$p-fail" 2 --expect-type llm

  say "D4b failed request where the gateway sets only tfy.error_type and error.type (OTLP status unset)"
  post --url "$url" --marker "TFYI$(uid)" --failure --no-error-status --resource "project_name=$p-errtype" --resource project_type=observe
  sleep 4; verify "$p-errtype" 2
  grep -q 'status=ERROR' "$OUT/verify-$p-errtype.txt" && note "UNEXPECTED: status ERROR with no OTLP status  $p-errtype" \
    || note "no ERROR status when only tfy.error_type is set  $p-errtype"

  say "D5 header and encoding variants against the same project"
  post --url "$url" --auth basic  --marker TFYH1 --resource "project_name=$p-auth" --resource project_type=observe
  post --url "$url" --auth bearer --marker TFYH2 --resource "project_name=$p-auth" || note "(expected) Bearer is rejected with 401"
  post --url "$url" --auth wrong  --marker TFYH2B --resource "project_name=$p-auth" || note "(expected) keys that belong to no account, 401"
  post --url "$url" --auth none   --marker TFYH3 --resource "project_name=$p-auth" || note "(expected) no credentials, 401"
  post --url "$url" --gzip        --marker TFYH4 --resource "project_name=$p-auth" || note "(expected) gzip bodies are rejected with 400"
  post --url "$url" --encoding json --marker TFYH5 --resource "project_name=$p-auth" --resource project_type=observe
  post --url "$FI_BASE_URL/tracer/v1/traces" --marker TFYH6 --resource "project_name=$p-auth" --resource project_type=observe
  if [ -n "${FI_GRPC_TARGET:-}" ]; then
    post --grpc "$FI_GRPC_TARGET" --marker TFYH7 --resource "project_name=$p-auth" --resource project_type=observe
    post --grpc "$FI_GRPC_TARGET" --auth basic --marker TFYH8 --resource "project_name=$p-auth" || note "(expected) over gRPC the collector reads x-api-key and x-secret-key metadata only, not Basic"
  fi
  sleep 4; verify "$p-auth" 8
}

# ---------------------------------------------------------------- through your own OpenTelemetry Collector
run_collector() {
  say "native export through the OpenTelemetry Collector recipe (real collector 0.162.0, SYNTHETIC batches)"
  local p="$P-collector" tap_host="${DOCKER_HOST_ALIAS:-host.docker.internal}"
  start_tap collector "$FI_BASE_URL"
  docker rm -f "$COLLECTOR_NAME" >/dev/null 2>&1 || true
  docker run -d --name "$COLLECTOR_NAME" --memory 512m \
    -p 127.0.0.1:14318:4318 -p 127.0.0.1:14317:4317 \
    -v "$HERE/native/otelcol.yaml:/etc/otelcol/config.yaml:ro" \
    -e FI_API_KEY -e FI_SECRET_KEY -e FI_PROJECT_NAME="$p" \
    -e FI_TRACES_URL="http://$tap_host:$TAP_PORT/v1/traces" \
    "otel/opentelemetry-collector-contrib:${OTELCOL_VERSION:-0.162.0}" --config /etc/otelcol/config.yaml >/dev/null
  local tries=0
  until curl -s -o /dev/null -m 2 http://127.0.0.1:14318/; do
    tries=$((tries + 1)); [ "$tries" -lt 60 ] || { echo "collector did not start"; docker logs "$COLLECTOR_NAME" 2>&1 | tail -20; exit 1; }
    sleep 1
  done
  local recv="http://127.0.0.1:14318/v1/traces"

  say "K1 gateway batch with no project_name and no keys: the collector names the project and adds the keys"
  local k1="TFYK$(uid)"
  env -u FI_API_KEY -u FI_SECRET_KEY "$PY" "$HERE/native/post_batch.py" --url "$recv" --auth none --marker "$k1" | tee -a "$SUMMARY"
  sleep 8; verify "$p" 2 --expect-type llm
  scan "$p" "$OUT/wire-collector.jsonl" absent "marker=$k1" "subject=$(echo "$k1" | tr 'A-Z' 'a-z')@example.test" "${PRIVACY_NEEDLES[@]}" || FAILED=1

  say "K2 same batch with content attributes ('exclude_literal': only the three documented keys already removed)"
  local k2="TFYL$(uid)"
  env -u FI_API_KEY -u FI_SECRET_KEY "$PY" "$HERE/native/post_batch.py" --url "$recv" --auth none --marker "$k2" --content exclude_literal | tee -a "$SUMMARY"
  sleep 8; scan "$p" "$OUT/wire-collector.jsonl" absent "marker=$k2" || FAILED=1

  say "K3 failed request with a synthetic exception event: ERROR status kept, error text and event details removed"
  local k3="TFYM$(uid)"
  env -u FI_API_KEY -u FI_SECRET_KEY "$PY" "$HERE/native/post_batch.py" --url "$recv" --auth none --marker "$k3" --failure --exception-event | tee -a "$SUMMARY"
  sleep 8; verify "$p" 6 --expect-type llm
  scan "$p" "$OUT/wire-collector.jsonl" absent "marker=$k3" "exc_message=exception.message" "exc_stack=exception.stacktrace" \
    "exc_path=/srv/tfy-llm-gateway" "error_message=tfy.error_message" "prompt_vars=tfy.prompt_variables" "teams=created_by_subject_teams" || FAILED=1
  grep -q 'status=ERROR' "$OUT/verify-$p.txt" && note "ERROR status kept  $p" || { note "ERROR status LOST  $p"; FAILED=1; }

  say "K4 gateway exporter that gzips: the collector accepts it and forwards plain OTLP"
  env -u FI_API_KEY -u FI_SECRET_KEY "$PY" "$HERE/native/post_batch.py" --url "$recv" --auth none --gzip --marker "TFYO$(uid)" | tee -a "$SUMMARY"

  say "K5 gRPC into the collector"
  env -u FI_API_KEY -u FI_SECRET_KEY "$PY" "$HERE/native/post_batch.py" --grpc 127.0.0.1:14317 --auth none --marker "TFYP$(uid)" | tee -a "$SUMMARY"
  sleep 8; verify "$p" 10 --expect-type llm
  stop_tap
  note "collector container memory/limits: $(docker inspect -f '{{.HostConfig.Memory}} bytes limit' "$COLLECTOR_NAME")"
  note "collector logs (warn+): $(docker logs "$COLLECTOR_NAME" 2>&1 | grep -ciE 'error|warn') line(s)"
}

case "$MODE" in
  client) run_client ;;
  native) run_native ;;
  collector) run_collector ;;
  all) run_client; run_native; run_collector ;;
  *) echo "usage: $0 [client|native|collector|all]"; exit 2 ;;
esac

say "summary"
cat "$SUMMARY"
[ "$FAILED" = 0 ] && echo "E2E OK" || { echo "E2E: one or more checks did not pass, see above"; exit 1; }
