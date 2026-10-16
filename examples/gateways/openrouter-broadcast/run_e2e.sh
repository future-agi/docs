#!/usr/bin/env bash
# End-to-end run of the OpenRouter Broadcast recipe against a self-hosted Future AGI.
#
#   source <env with FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL, CLIPROXY_API_KEY, CLIPROXY_OPENAI_BASE_URL>
#   PYTHON=/path/to/venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh [direct|collector|all]
#
# What is real and what is not:
#   real     the OpenTelemetry Collector container running otelcol.yaml, the Future AGI collector and storage
#            you point it at, and (with --live) the model calls behind each generation
#   STAND-IN OpenRouter. standin_openrouter.py posts what OpenRouter's documentation says Broadcast posts. No
#            OpenRouter account, key, tunnel or code is involved, and nothing here was captured from OpenRouter.
#
# Needs: Docker, a self-hosted Future AGI in Docker (the scan reads its Postgres and ClickHouse containers; set
#   FI_PG_CONTAINER and FI_CH_CONTAINER if yours are named differently, or SKIP_SCAN=1), Python 3.10+, and
#   `pip install -r requirements-test.txt` for the wire tap.
# Environment (defaults in brackets):
#   PYTHON [python3]  OUT [./evidence]  PROJECT [th8103-rest-openrouter-broadcast]  RUN_ID [empty: fixed names]
#   OTELCOL_VERSION [0.162.0]   STANDIN_UPSTREAM_BASE_URL / STANDIN_UPSTREAM_API_KEY [CLIPROXY_*]   STANDIN_MODEL [gpt-6-luna]
#   VERIFY    path to fi_verify.py of the local stack (optional; skipped when unset)
#   SKIP_SCAN=1  skip the stored-rows scan   SKIP_CROSS_WS=1  skip the second-workspace check (writes Postgres rows)
# Content is never printed; evidence files can contain prompts and stay out of git.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
BASE="${PROJECT:-th8103-rest-openrouter-broadcast}"
P="$BASE${RUN_ID:+-$RUN_ID}"
OTELCOL_VERSION="${OTELCOL_VERSION:-0.162.0}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL}"
export STANDIN_UPSTREAM_BASE_URL="${STANDIN_UPSTREAM_BASE_URL:-${CLIPROXY_OPENAI_BASE_URL:-}}"
export STANDIN_UPSTREAM_API_KEY="${STANDIN_UPSTREAM_API_KEY:-${CLIPROXY_API_KEY:-}}"
export STANDIN_MODEL="${STANDIN_MODEL:-gpt-6-luna}"
CNAME="th8103-rest-openrouter-broadcast-otelcol"
TAP_PORT=18244
RECV_PORT=14418
HOST_ALIAS="${DOCKER_HOST_ALIAS:-host.docker.internal}"
# The secret OpenRouter's Headers field would carry. Invented per run, never printed.
BROADCAST_TOKEN="brd-$("$PY" -c 'import secrets; print(secrets.token_hex(16))')"
export BROADCAST_TOKEN BROADCAST_AUTH="Bearer $BROADCAST_TOKEN" WRONG_AUTH="Bearer not-the-token"
mkdir -p "$OUT"
SUMMARY="$OUT/summary-$MODE.txt"; : > "$SUMMARY"
FAILED=0; PIDS=(); STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

say() { printf '\n== %s\n' "$*"; }
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
uid() { "$PY" -c 'import secrets; print(secrets.token_hex(5).upper())'; }
fail() { note "CHECK FAILED: $*"; FAILED=1; }
cleanup() {
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null || true; done
  docker rm -f "$CNAME" >/dev/null 2>&1 || true
  [ -f "$OUT/ws2.json" ] && "$PY" "$HERE/tools/second_workspace.py" remove >/dev/null 2>&1 || true
}
trap cleanup EXIT

SO() { "$PY" "$HERE/standin_openrouter.py" "$@"; }
FIH=(--header X-Api-Key=FI_API_KEY --header X-Secret-Key=FI_SECRET_KEY)

status_of() { sed -n 's/.*"status": \([0-9]*\).*/\1/p' | sort -u | tr '\n' ' ' | sed 's/ $//'; }
expect() { # label expected-status command...   (runs the command, records its output, compares the HTTP status)
  local label="$1" want="$2"; shift 2
  local out got; out="$("$@" 2>&1)"; got="$(printf '%s\n' "$out" | status_of)"
  printf '%s\n' "$out" | cut -c1-220 >> "$OUT/http-$MODE.log"
  if [ "$got" = "$want" ]; then note "OK   $label -> HTTP $got"; else note "FAIL $label -> HTTP ${got:-none}, expected $want"; FAILED=1; fi
}

verify() { # project min-spans [extra fi_verify args...]
  local project="$1" min="$2"; shift 2
  if [ -z "${VERIFY:-}" ]; then note "fi_verify skipped (VERIFY not set)  $project"; return; fi
  "$PY" "$VERIFY" --project "$project" --wait 90 --min-spans "$min" --json "$OUT/spans-$project.json" "$@" >"$OUT/verify-$project.txt" 2>&1 || true
  sed -n '1,22p' "$OUT/verify-$project.txt" | cut -c1-200
  if grep -q '^PASS' "$OUT/verify-$project.txt"; then note "fi_verify PASS  $project"; else note "fi_verify FAIL  $project"; FAILED=1; fi
}

scan() { # project wire-file expect(found|absent) needle...
  local project="$1" wire="$2" expect="$3"; shift 3
  if [ "${SKIP_SCAN:-0}" = 1 ]; then note "scan skipped  $project"; return 0; fi
  local args=(--project "$project" --ignore-case --json "$OUT/scan-$project-$expect.json")
  [ -n "$wire" ] && args+=(--wire "$wire")
  [ "$expect" = found ] && args+=(--expect-found)
  for n in "$@"; do args+=(--needle "$n"); done
  if "$PY" -I "$HERE/tools/scan_local_stack.py" "${args[@]}" | tee "$OUT/scanlog-$project-$expect.txt"; then
    note "scan expected-$expect OK  $project"
  else
    note "scan expected-$expect NOT MET  $project"; FAILED=1
  fi
}

start_tap() { # name
  rm -f "$OUT/wire-$1.jsonl"
  "$PY" "$HERE/tools/wire_tap.py" --listen "$TAP_PORT" --forward "$FI_BASE_URL" --out "$OUT/wire-$1.jsonl" >"$OUT/tap-$1.log" 2>&1 &
  TAP_PID=$!; PIDS+=("$TAP_PID"); sleep 1
}
stop_tap() { kill "$TAP_PID" 2>/dev/null || true; wait "$TAP_PID" 2>/dev/null || true; }

save_logs() { # tag   (keeps the collector's own log; checked for secrets at the end)
  docker logs "$CNAME" > "$OUT/collector-$1.log" 2>&1 || true
}

start_collector() { # project capture(true|false) fi-key-env-prefix(FI|BAD) traces-url
  local project="$1" capture="$2" keys="$3" url="$4" key="$FI_API_KEY" secret="$FI_SECRET_KEY"
  [ "$keys" = BAD ] && key="not-a-key" && secret="not-a-secret"
  docker rm -f "$CNAME" >/dev/null 2>&1 || true
  while docker inspect "$CNAME" >/dev/null 2>&1; do sleep 1; done
  docker run -d --name "$CNAME" --memory 512m -p 127.0.0.1:$RECV_PORT:4318 \
    -v "$HERE/otelcol.yaml:/etc/otelcol/config.yaml:ro" \
    -e BROADCAST_TOKEN -e FI_API_KEY="$key" -e FI_SECRET_KEY="$secret" -e FI_PROJECT_NAME="$project" \
    -e FI_CAPTURE_CONTENT="$capture" -e FI_TRACES_URL="$url" \
    "otel/opentelemetry-collector-contrib:$OTELCOL_VERSION" --config /etc/otelcol/config.yaml >/dev/null || { fail "collector did not start"; return 1; }
  local tries=0
  until SO probe --endpoint "http://127.0.0.1:$RECV_PORT/v1/traces" --header Authorization=BROADCAST_AUTH >/dev/null 2>&1; do
    tries=$((tries + 1)); [ "$tries" -lt 60 ] || { docker logs "$CNAME" 2>&1 | tail -20; fail "collector not ready"; return 1; }
    sleep 1
  done
}
RECV="http://127.0.0.1:$RECV_PORT/v1/traces"
# The collector runs in Docker, where "localhost" is the container itself.
FI_URL_FROM_DOCKER="${FI_BASE_URL/localhost/$HOST_ALIAS}"; FI_URL_FROM_DOCKER="${FI_URL_FROM_DOCKER/127.0.0.1/$HOST_ALIAS}"

PRIVACY_NEEDLES=(
  "username=$(id -un)" "hostname=$(hostname)" "shorthost=$(hostname -s)"
  "home=$HOME" "cwd=$PWD" "traceback=Traceback" "stackpath=/srv/orb-gateway"
)

# ---------------------------------------------------------------- Broadcast straight to Future AGI, no collector
run_direct() {
  local url="$FI_BASE_URL/v1/traces" p="$P-direct"
  say "direct: the destination pointed straight at the Future AGI collector (STAND-IN sender)"
  expect "D1 Test Connection, X-Api-Key + X-Secret-Key" 200 SO probe --endpoint "$url" "${FIH[@]}"
  expect "D2 Test Connection, keys that belong to no account" 401 env WRONG_KEY=x "$PY" "$HERE/standin_openrouter.py" probe --endpoint "$url" --header X-Api-Key=WRONG_KEY --header X-Secret-Key=WRONG_KEY
  expect "D3 Test Connection, Authorization: Bearer <api key> (OpenRouter's documented header shape)" 401 env BEARER="Bearer $FI_API_KEY" "$PY" "$HERE/standin_openrouter.py" probe --endpoint "$url" --header Authorization=BEARER
  expect "D3b Test Connection, no headers" 401 SO probe --endpoint "$url"
  expect "D4 generation without project_name" 400 SO send --endpoint "$url" "${FIH[@]}" --scenario success --marker "ORBD4$(uid)"
  local d5="ORBD5$(uid)"
  expect "D5 generation with project_name set by the sender (STAND-IN for a stamp)" 200 SO send --endpoint "$url" "${FIH[@]}" --scenario success --marker "$d5" --resource "project_name=$p" --resource project_type=observe
  expect "D6 same body gzipped" 400 SO send --endpoint "$url" "${FIH[@]}" --gzip --scenario success --marker "ORBD6$(uid)" --resource "project_name=$p"
  expect "D7 the /tracer/v1/traces path" 200 SO send --endpoint "$FI_BASE_URL/tracer/v1/traces" "${FIH[@]}" --scenario success --marker "ORBD7$(uid)" --resource "project_name=$p"
  local d8="ORBD8$(uid)"
  expect "D8 the same body twice (same trace id and span ids)" 200 SO send --endpoint "$url" "${FIH[@]}" --scenario success --marker "$d8" --repeat 2 --resource "project_name=$p-dup" --resource project_type=observe
  expect "D9 about 18 MB body (two 9M-character copies of the prompt), over the 16 MiB Future AGI reads per request" 413 SO send --endpoint "$url" "${FIH[@]}" --scenario success --big-chars 9000000 --marker "ORBD9B$(uid)" --resource "project_name=$p-big"
  sleep 6
  verify "$p" 4 --expect-type llm
  scan "$p" "" found "marker=$d5" || true
  verify "$p-dup" 2
  note "(info) same trace id and span ids posted twice: $(grep -c '^trace ' "$OUT/verify-$p-dup.txt") trace, $(grep -c '^[[:space:]]*- \[' "$OUT/verify-$p-dup.txt") spans stored"

  if [ "${SKIP_CROSS_WS:-0}" != 1 ]; then
    say "direct: a key from a second workspace uses the name of a project that exists in the first"
    "$PY" "$HERE/tools/second_workspace.py" create --out "$OUT/ws2.json" | tee -a "$SUMMARY"
    export WS2_KEY WS2_SECRET
    WS2_KEY="$("$PY" -c "import json;print(json.load(open('$OUT/ws2.json'))['api_key'])")"
    WS2_SECRET="$("$PY" -c "import json;print(json.load(open('$OUT/ws2.json'))['secret_key'])")"
    echo "before:" | tee -a "$SUMMARY"; "$PY" "$HERE/tools/second_workspace.py" counts --name "$p" | tee -a "$SUMMARY"
    expect "X1 second-workspace key, project name from the first workspace" 200 SO send --endpoint "$url" --header X-Api-Key=WS2_KEY --header X-Secret-Key=WS2_SECRET --scenario success --marker "ORBX1$(uid)" --resource "project_name=$p" --resource project_type=observe
    sleep 6
    echo "after:" | tee -a "$SUMMARY"; "$PY" "$HERE/tools/second_workspace.py" counts --name "$p" | tee -a "$SUMMARY" > "$OUT/crossws-after.txt"
    "$PY" "$HERE/tools/second_workspace.py" remove | tee -a "$SUMMARY"; rm -f "$OUT/ws2.json"
  fi
}

# ---------------------------------------------------------------- Broadcast -> your collector -> Future AGI (the recipe)
run_collector() {
  say "collector: otel/opentelemetry-collector-contrib:$OTELCOL_VERSION with otelcol.yaml, content OFF (the default)"
  start_tap off
  start_collector "$P" false FI "http://$HOST_ALIAS:$TAP_PORT/v1/traces" || return 1
  docker run --rm --entrypoint /otelcol-contrib "otel/opentelemetry-collector-contrib:$OTELCOL_VERSION" --version 2>&1 | head -1 | tee -a "$SUMMARY"

  expect "K1a Test Connection, no Authorization header" 401 SO probe --endpoint "$RECV"
  expect "K1b Test Connection, wrong token" 401 SO probe --endpoint "$RECV" --header Authorization=WRONG_AUTH
  expect "K1c Test Connection, right token" 200 SO probe --endpoint "$RECV" --header Authorization=BROADCAST_AUTH

  local m1="ORBA$(uid)" m2="ORBB$(uid)"
  say "K2 two real model calls (tool call, then answer) reported as two Broadcast generations; custom metadata marker $m2 (not content-gated)"
  expect "K2 live generations" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario success --live --marker "$m1" --meta-marker "$m2" --cost-metadata --out "$OUT/sent-$P.jsonl"

  local m3="ORBC$(uid)"
  say "K3 failed request, with a synthetic exception event"
  expect "K3 error generation" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario error --marker "$m3" --exception-event --out "$OUT/sent-$P.jsonl"

  local m4="ORBD$(uid)"
  say "K4 the sender's own Privacy Mode on (prompt and completion already stripped by OpenRouter)"
  expect "K4 privacy-mode generation" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario privacy --marker "$m4" --cost-metadata --out "$OUT/sent-$P.jsonl"

  say "K5 token keys spelled prompt_tokens / completion_tokens (OpenRouter's Webhook example), and no usage at all"
  expect "K5a legacy token keys" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario legacy --marker "ORBE$(uid)"
  expect "K5b no usage fields" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario no-usage --marker "ORBF$(uid)"

  say "K6 gzipped body, and a generation nested under the caller's own trace"
  expect "K6a gzip" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --gzip --scenario success --marker "ORBG$(uid)"
  local nested_trace; nested_trace="$("$PY" -c 'import secrets; print(secrets.token_hex(16))')"   # random: fixed ids collide with other test runs
  expect "K6b nested (trace_id + parent_span_id + span_name)" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario nested --marker "ORBH$(uid)" \
    --trace-id "$nested_trace" --parent-span-id 0123456789abcdef

  sleep 10
  stop_tap
  note "collector memory after the content-off run: $(docker stats --no-stream --format '{{.MemUsage}}' "$CNAME") (limit 512m)"
  save_logs off
  verify "$P" 17 --expect-type llm --expect-type chain
  grep -q 'status=ERROR' "$OUT/verify-$P.txt" 2>/dev/null && note "ERROR status present  $P" || fail "no ERROR status in $P"
  if grep -q '\[chain\] Summarization Step' "$OUT/verify-$P.txt" 2>/dev/null && grep -q '\[llm\] Generate Summary' "$OUT/verify-$P.txt" 2>/dev/null; then
    note "nested hierarchy present: Document Processing > Summarization Step > Generate Summary  $P"
  else
    fail "nested hierarchy missing in $P"
  fi
  for want in "tok=9/4" "model=openai/gpt-6-luna"; do
    grep -q -- "$want" "$OUT/verify-$P.txt" 2>/dev/null && note "found '$want' in the span tree" || fail "'$want' missing from the span tree"
  done
  note "privacy proof, content OFF: the markers below were in the prompts, completions, tool result and error text; custom metadata '$m2' is expected to be stored"
  scan "$P" "$OUT/wire-off.jsonl" absent "marker_live=$m1" "marker_error=$m3" "marker_privacy=$m4" "marker_error_user=$(echo "$m3" | tr 'A-Z' 'a-z')@example.test" \
    "note_marker=${m1}-note" "${PRIVACY_NEEDLES[@]}" || true
  scan "$P" "$OUT/wire-off.jsonl" found "metadata_marker=$m2" "user_id=user_12345" || true

  say "collector: the same recipe with FI_CAPTURE_CONTENT=true (the documented opt-in)"
  local po="$P-optin" m5="ORBI$(uid)"
  start_tap on
  start_collector "$po" true FI "http://$HOST_ALIAS:$TAP_PORT/v1/traces" || return 1
  expect "O1 live generations, content on" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario success --live --marker "$m5"
  expect "O2 error generation, content on" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario error --marker "ORBJ$(uid)" --exception-event
  say "O3 a very large generation with content on: about 18 MB once exported, over the 16 MiB Future AGI reads per request"
  expect "O3 large generation accepted by the collector" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario success --big-chars 9000000 --marker "ORBL$(uid)"
  sleep 12; stop_tap
  save_logs on
  if grep -q 'Dropping data' "$OUT/collector-on.log" && grep -q '413' "$OUT/collector-on.log"; then
    note "OK   the oversized export was dropped by the collector with HTTP 413 and logged"
  else
    fail "no 413 drop in the collector log for the oversized generation"
  fi
  verify "$po" 4 --expect-type llm
  scan "$po" "$OUT/wire-on.jsonl" found "marker=$m5" "error_text=Provider returned 429" || true
  if grep -E '\- \[llm\].*in=[1-9][0-9]*B' "$OUT/verify-$po.txt" >/dev/null 2>&1; then note "Input pane filled (input.value) with content on  $po"; else fail "Input pane empty with content on  $po"; fi

  say "collector: wrong Future AGI keys behind a collector whose Test Connection still passes"
  local pb="$P-badkeys"
  start_collector "$pb" false BAD "$FI_URL_FROM_DOCKER/v1/traces" || return 1
  expect "B1 Test Connection through the collector with wrong Future AGI keys" 200 SO probe --endpoint "$RECV" --header Authorization=BROADCAST_AUTH
  expect "B2 generation accepted by the collector" 200 SO send --endpoint "$RECV" --header Authorization=BROADCAST_AUTH --scenario success --marker "ORBK$(uid)"
  sleep 8
  save_logs badkeys
  grep -E 'Dropping data|Unauthenticated|401' "$OUT/collector-badkeys.log" | head -2 | cut -c1-120 | sed 's/^/(info) collector log: /' | tee -a "$SUMMARY" || true
  grep -q 'Dropping data' "$OUT/collector-badkeys.log" && note "OK   the collector logged the rejected export (no header values in it)" || fail "collector log shows no rejected export"
  if "$PY" -I "$HERE/tools/scan_local_stack.py" --project "$pb" --needle x >/dev/null 2>&1; [ $? -eq 2 ]; then note "no project or span stored for $pb"; else fail "something was stored for $pb"; fi

  say "no secret in any log"
  docker logs "${FI_APP_CONTAINER:-th8103-e2e-app-1}" --since "$STARTED_AT" > "$OUT/fi-app.log" 2>&1 || true
  for f in "$OUT"/collector-off.log "$OUT"/collector-on.log "$OUT"/collector-badkeys.log "$OUT/fi-app.log"; do
    hits=0
    for secret in "$BROADCAST_TOKEN" "$FI_API_KEY" "$FI_SECRET_KEY"; do
      c="$(grep -c -F -- "$secret" "$f" 2>/dev/null || true)"; hits=$((hits + ${c:-0}))
    done
    [ "$hits" = 0 ] && note "secrets absent from $(basename "$f") ($(wc -l < "$f" | tr -d ' ') lines)" || fail "secret found in $(basename "$f")"
  done
  note "collector memory limit: $(docker inspect -f '{{.HostConfig.Memory}}' "$CNAME") bytes"
}

case "$MODE" in
  direct) run_direct ;;
  collector) run_collector ;;
  all) run_direct; run_collector ;;
  *) echo "usage: $0 [direct|collector|all]"; exit 2 ;;
esac

say "summary"
cat "$SUMMARY"
[ "$FAILED" = 0 ] && echo "E2E OK" || { echo "E2E: one or more checks did not pass, see above"; exit 1; }
