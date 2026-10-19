#!/usr/bin/env bash
# End-to-end run of the Cloudflare AI Gateway recipe against a self-hosted Future AGI.
#
#   source <env with FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL, CLIPROXY_API_KEY, CLIPROXY_OPENAI_BASE_URL>
#   PYTHON=/path/to/venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh [direct|collector|replay|all]
#
# What is real and what is not:
#   real     the OpenTelemetry Collector container running otelcol.yaml, the Future AGI collector and storage
#            you point it at, (with --live) the model call behind each gateway request, and in `replay` the
#            payloads a real Cloudflare AI Gateway exported on 2026-10-18 (tests/fixtures/)
#   STAND-IN in `direct` and `collector`: standin_cloudflare.py posts the span shape the real gateway sent, from
#            your machine, so the run needs no Cloudflare account. Its error scenario is SYNTHETIC: the real
#            gateway exported no span for a failed request.
#
# Needs: Docker, a self-hosted Future AGI in Docker (the scan reads its Postgres and ClickHouse containers; set
#   FI_PG_CONTAINER and FI_CH_CONTAINER if yours are named differently, or SKIP_SCAN=1), Python 3.10+, and
#   `pip install -r requirements-test.txt` for the wire tap and protobuf bodies.
# Environment (defaults in brackets):
#   PYTHON [python3]  OUT [./evidence]  PROJECT [th8103-rest-cloudflare-ai-gateway]  RUN_ID [empty: fixed names]
#   OTELCOL_VERSION [0.162.0]   STANDIN_UPSTREAM_BASE_URL / STANDIN_UPSTREAM_API_KEY [CLIPROXY_*]   STANDIN_MODEL [gpt-6-luna]
#   VERIFY    path to fi_verify.py of the local stack (optional; skipped when unset)
#   SKIP_SCAN=1  skip the stored-rows scan
# Content is never printed; evidence files can contain prompts and stay out of git.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
BASE="${PROJECT:-th8103-rest-cloudflare-ai-gateway}"
P="$BASE${RUN_ID:+-$RUN_ID}"
OTELCOL_VERSION="${OTELCOL_VERSION:-0.162.0}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL}"
export STANDIN_UPSTREAM_BASE_URL="${STANDIN_UPSTREAM_BASE_URL:-${CLIPROXY_OPENAI_BASE_URL:-}}"
export STANDIN_UPSTREAM_API_KEY="${STANDIN_UPSTREAM_API_KEY:-${CLIPROXY_API_KEY:-}}"
export STANDIN_MODEL="${STANDIN_MODEL:-gpt-6-luna}"
CNAME="${OTELCOL_CONTAINER:-th8103-rest-cloudflare-ai-gateway-otelcol}"
TAP_PORT="${TAP_PORT:-18299}"
RECV_PORT="${RECV_PORT:-14499}"
HOST_ALIAS="${DOCKER_HOST_ALIAS:-host.docker.internal}"
# The secret the exporter's Headers field would carry. Invented per run, never printed.
GATEWAY_TOKEN="cfg-$("$PY" -c 'import secrets; print(secrets.token_hex(16))')"
export GATEWAY_TOKEN GATEWAY_AUTH="Bearer $GATEWAY_TOKEN" WRONG_AUTH="Bearer not-the-token"
mkdir -p "$OUT"
SUMMARY="$OUT/summary-$MODE.txt"; : > "$SUMMARY"
FAILED=0; PIDS=(); STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

say() { printf '\n== %s\n' "$*"; }
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
uid() { "$PY" -c 'import secrets; print(secrets.token_hex(5).upper())'; }
hex() { "$PY" -c "import secrets; print(secrets.token_hex($1))"; }
fail() { note "CHECK FAILED: $*"; FAILED=1; }
cleanup() {
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null || true; done
  docker rm -f "$CNAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

CF() { "$PY" "$HERE/standin_cloudflare.py" "$@"; }
FIH=(--header X-Api-Key=FI_API_KEY --header X-Secret-Key=FI_SECRET_KEY)

status_of() { sed -n 's/.*"status": \([0-9]*\).*/\1/p' | sort -u | tr '\n' ' ' | sed 's/ $//'; }
expect() { # label expected-status command...
  local label="$1" want="$2"; shift 2
  local out got; out="$("$@" 2>&1)"; got="$(printf '%s\n' "$out" | status_of)"
  printf '%s\n' "$out" | cut -c1-260 >> "$OUT/http-$MODE.log"
  if [ "$got" = "$want" ]; then note "OK   $label -> HTTP $got"; else note "FAIL $label -> HTTP ${got:-none}, expected $want"; FAILED=1; fi
}

verify() { # project min-spans [extra fi_verify args...]
  local project="$1" min="$2"; shift 2
  if [ -z "${VERIFY:-}" ]; then note "fi_verify skipped (VERIFY not set)  $project"; return; fi
  # A shared, memory-capped ClickHouse can answer "memory limit exceeded" to a read; that is not a verdict, so retry.
  local attempt
  for attempt in 1 2 3 4 5 6; do
    "$PY" "$VERIFY" --project "$project" --wait 90 --min-spans "$min" --json "$OUT/spans-$project.json" "$@" >"$OUT/verify-$project.txt" 2>&1 || true
    grep -q 'memory limit exceeded' "$OUT/verify-$project.txt" || break
    note "(info) ClickHouse memory limit on read, retry $attempt  $project"; sleep 45
  done
  sed -n '1,24p' "$OUT/verify-$project.txt" | cut -c1-200
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
save_logs() { docker logs "$CNAME" > "$OUT/collector-$1.log" 2>&1 || true; }

start_collector() { # project capture(true|false) fi-keys(FI|BAD) traces-url
  local project="$1" capture="$2" keys="$3" url="$4" key="$FI_API_KEY" secret="$FI_SECRET_KEY"
  [ "$keys" = BAD ] && key="not-a-key" && secret="not-a-secret"
  docker rm -f "$CNAME" >/dev/null 2>&1 || true
  while docker inspect "$CNAME" >/dev/null 2>&1; do sleep 1; done
  docker run -d --name "$CNAME" --memory 512m -p 127.0.0.1:$RECV_PORT:4318 \
    -v "$HERE/otelcol.yaml:/etc/otelcol/config.yaml:ro" \
    -e GATEWAY_TOKEN -e FI_API_KEY="$key" -e FI_SECRET_KEY="$secret" -e FI_PROJECT_NAME="$project" \
    -e FI_CAPTURE_CONTENT="$capture" -e FI_TRACES_URL="$url" \
    "otel/opentelemetry-collector-contrib:$OTELCOL_VERSION" --config /etc/otelcol/config.yaml >/dev/null || { fail "collector did not start"; return 1; }
  local tries=0
  # ready = the port answers (401 without the token is an answer)
  until curl -s -o /dev/null -X POST -H 'Content-Type: application/json' -d '{"resourceSpans":[]}' "http://127.0.0.1:$RECV_PORT/v1/traces"; do
    tries=$((tries + 1)); [ "$tries" -lt 60 ] || { docker logs "$CNAME" 2>&1 | tail -20; fail "collector not ready"; return 1; }
    sleep 1
  done
}
RECV="http://127.0.0.1:$RECV_PORT/v1/traces"
FI_URL_FROM_DOCKER="${FI_BASE_URL/localhost/$HOST_ALIAS}"; FI_URL_FROM_DOCKER="${FI_URL_FROM_DOCKER/127.0.0.1/$HOST_ALIAS}"

PRIVACY_NEEDLES=(
  "username=$(id -un)" "hostname=$(hostname)" "shorthost=$(hostname -s)"
  "home=$HOME" "cwd=$PWD" "traceback=Traceback" "stackpath=/srv/cf-gateway"
)

# ---------------------------------------------------------------- exporter straight at Future AGI, no collector
run_direct() {
  local url="$FI_BASE_URL/v1/traces" p="$P-direct"
  say "direct: the exporter pointed straight at the Future AGI collector (STAND-IN sender)"
  expect "D1 export, X-Api-Key + X-Secret-Key, no project_name" 400 CF send --endpoint "$url" "${FIH[@]}" --marker "CFGD1$(uid)"
  expect "D2 export, wrong keys" 401 env WRONG_KEY=x "$PY" "$HERE/standin_cloudflare.py" send --endpoint "$url" --header X-Api-Key=WRONG_KEY --header X-Secret-Key=WRONG_KEY --marker "CFGD2$(uid)" --resource "project_name=$p"
  expect "D3 export, Authorization: Bearer <api key> (the shape Cloudflare's page shows)" 401 env BEARER="Bearer $FI_API_KEY" "$PY" "$HERE/standin_cloudflare.py" send --endpoint "$url" --header Authorization=BEARER --marker "CFGD3$(uid)" --resource "project_name=$p"
  expect "D3b export, no headers" 401 CF send --endpoint "$url" --marker "CFGD3B$(uid)" --resource "project_name=$p"
  local d4="CFGD4$(uid)"
  expect "D4 JSON with project_name set by the sender (STAND-IN for a stamp)" 200 CF send --endpoint "$url" "${FIH[@]}" --live --marker "$d4" --resource "project_name=$p" --resource project_type=observe
  expect "D5 protobuf with project_name" 200 CF send --endpoint "$url" "${FIH[@]}" --content-type protobuf --marker "CFGD5$(uid)" --resource "project_name=$p"
  expect "D6 JSON gzipped" 400 CF send --endpoint "$url" "${FIH[@]}" --gzip --marker "CFGD6$(uid)" --resource "project_name=$p"
  expect "D7 the /tracer/v1/traces path" 200 CF send --endpoint "$FI_BASE_URL/tracer/v1/traces" "${FIH[@]}" --marker "CFGD7$(uid)" --resource "project_name=$p"
  expect "D8 no prompt in the span" 200 CF send --endpoint "$url" "${FIH[@]}" --scenario no-prompt --marker "CFGD8$(uid)" --resource "project_name=$p"
  sleep 6
  verify "$p" 4
  scan "$p" "" found "marker=$d4" || true
}

# ---------------------------------------------------------------- exporter -> your collector -> Future AGI (the recipe)
run_collector() {
  say "collector: otel/opentelemetry-collector-contrib:$OTELCOL_VERSION with otelcol.yaml, content OFF (the default)"
  start_tap off
  start_collector "$P" false FI "http://$HOST_ALIAS:$TAP_PORT/v1/traces" || return 1
  docker run --rm --entrypoint /otelcol-contrib "otel/opentelemetry-collector-contrib:$OTELCOL_VERSION" --version 2>&1 | head -1 | tee -a "$SUMMARY"

  expect "K1a export, no Authorization header" 401 CF send --endpoint "$RECV" --marker "CFGK1A$(uid)"
  expect "K1b export, wrong token" 401 CF send --endpoint "$RECV" --header Authorization=WRONG_AUTH --marker "CFGK1B$(uid)"

  local m1="CFGA$(uid)" m2="CFGB$(uid)"
  say "K2 a real model call reported as a gateway span, JSON (the default); custom metadata marker $m2 (not content-gated)"
  expect "K2 live request, JSON" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --live --marker "$m1" --meta-marker "$m2" --out "$OUT/sent-$P.jsonl"
  expect "K2b live request, protobuf" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --live --content-type protobuf --marker "${m1}P" --out "$OUT/sent-$P.jsonl"

  local m3="CFGC$(uid)"
  say "K3 failed request, with a synthetic exception event"
  expect "K3 error request" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --scenario error --marker "$m3" --exception-event --out "$OUT/sent-$P.jsonl"

  say "K4 usage missing, prompt missing, gzipped body"
  expect "K4a no usage fields" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --scenario no-usage --marker "CFGE$(uid)"
  expect "K4b no prompt" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --scenario no-prompt --marker "CFGF$(uid)"
  expect "K4c gzip" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --gzip --marker "CFGG$(uid)"

  say "K5 gateway span linked to an application trace (cf-aig-otel-trace-id and cf-aig-otel-parent-span-id)"
  local tid sid; tid="$(hex 16)"; sid="$(hex 8)"
  expect "K5a the application's own parent span, sent straight to Future AGI" 200 CF caller --endpoint "$FI_BASE_URL/v1/traces" "${FIH[@]}" --trace-id "$tid" --span-id "$sid" --resource "project_name=$P"
  expect "K5b the linked gateway span, through the collector" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --live --marker "CFGH$(uid)" --otel-trace-id "$tid" --otel-parent-span-id "$sid" --out "$OUT/sent-$P.jsonl"
  note "linked trace id (sent as cf-aig-otel-trace-id): $tid"

  sleep 10
  stop_tap
  note "collector memory after the content-off run: $(docker stats --no-stream --format '{{.MemUsage}}' "$CNAME") (limit 512m)"
  save_logs off
  verify "$P" 8 --expect-type llm --expect-type chain   # K2, K2b, K3, K4a-c, K5a, K5b: eight spans
  grep -q 'status=ERROR' "$OUT/verify-$P.txt" 2>/dev/null && note "ERROR status present  $P" || fail "no ERROR status in $P"
  grep -q -- "$tid" <(tr -d '-' < "$OUT/verify-$P.txt") && note "linked trace stored under the id the caller sent  $P" || fail "linked trace id not found in $P"
  for want in "tok=" "model=gpt-6-luna"; do
    grep -q -- "$want" "$OUT/verify-$P.txt" 2>/dev/null && note "found '$want' in the span tree" || fail "'$want' missing from the span tree"
  done
  note "privacy proof, content OFF: the markers below were in the prompts, completions and error text; custom metadata '$m2' is expected to be stored"
  scan "$P" "$OUT/wire-off.jsonl" absent "marker_live=$m1" "marker_live_pb=${m1}P" "marker_error=$m3" "marker_error_user=$(echo "$m3" | tr 'A-Z' 'a-z')@example.test" \
    "note_marker=${m1}-note" "${PRIVACY_NEEDLES[@]}" || true
  scan "$P" "$OUT/wire-off.jsonl" found "metadata_marker=$m2" "team=engineering" || true

  say "collector: the same recipe with FI_CAPTURE_CONTENT=true (the documented opt-in)"
  local po="$P-optin" m5="CFGI$(uid)"
  start_tap on
  start_collector "$po" true FI "http://$HOST_ALIAS:$TAP_PORT/v1/traces" || return 1
  expect "O1 live request, content on" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --live --marker "$m5"
  expect "O2 error request, content on" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --scenario error --marker "CFGJ$(uid)" --exception-event
  sleep 12; stop_tap
  save_logs on
  verify "$po" 2 --expect-type llm
  scan "$po" "$OUT/wire-on.jsonl" found "marker=$m5" "error_text=Provider returned 429" || true
  if grep -E '\- \[llm\].*in=[1-9][0-9]*B' "$OUT/verify-$po.txt" >/dev/null 2>&1; then note "Input pane filled (input.value) with content on  $po"; else fail "Input pane empty with content on  $po"; fi
  if grep -E '\- \[llm\].*out=[1-9][0-9]*B' "$OUT/verify-$po.txt" >/dev/null 2>&1; then note "Output pane filled (output.value) with content on  $po"; else fail "Output pane empty with content on  $po"; fi

  say "collector: wrong Future AGI keys behind a collector that still accepts the gateway's token"
  local pb="$P-badkeys"
  start_collector "$pb" false BAD "$FI_URL_FROM_DOCKER/v1/traces" || return 1
  expect "B1 export accepted by the collector" 200 CF send --endpoint "$RECV" --header Authorization=GATEWAY_AUTH --marker "CFGK$(uid)"
  sleep 8
  save_logs badkeys
  grep -E 'Dropping data|Unauthenticated|401' "$OUT/collector-badkeys.log" | head -2 | cut -c1-120 | sed 's/^/(info) collector log: /' | tee -a "$SUMMARY" || true
  grep -q 'Dropping data' "$OUT/collector-badkeys.log" && note "OK   the collector logged the rejected export (no header values in it)" || fail "collector log shows no rejected export"
  if "$PY" -I "$HERE/tools/scan_local_stack.py" --project "$pb" --needle x >/dev/null 2>&1; [ $? -eq 2 ]; then note "no project or span stored for $pb"; else fail "something was stored for $pb"; fi

  say "no secret in any log"
  docker logs "${FI_APP_CONTAINER:-th8103-e2e-app-1}" --since "$STARTED_AT" > "$OUT/fi-app.log" 2>&1 || true
  for f in "$OUT"/collector-off.log "$OUT"/collector-on.log "$OUT"/collector-badkeys.log "$OUT/fi-app.log"; do
    hits=0
    for secret in "$GATEWAY_TOKEN" "$FI_API_KEY" "$FI_SECRET_KEY"; do
      c="$(grep -c -F -- "$secret" "$f" 2>/dev/null || true)"; hits=$((hits + ${c:-0}))
    done
    [ "$hits" = 0 ] && note "secrets absent from $(basename "$f") ($(wc -l < "$f" | tr -d ' ') lines)" || fail "secret found in $(basename "$f")"
  done
  note "collector memory limit: $(docker inspect -f '{{.HostConfig.Memory}}' "$CNAME") bytes"
}

# ---------------------------------------------------------------- real Cloudflare payloads (tests/fixtures) -> collector
replay_fixtures() { # posts every captured payload once, each under a fresh trace id
  "$PY" -I - "$RECV" "$HERE/tests/fixtures" <<'PYEOF'
import json, os, secrets, sys, urllib.error, urllib.request
url, d = sys.argv[1], sys.argv[2]
for name in sorted(os.listdir(d)):
    if not (name.startswith("cloudflare-") and name.endswith(".json")):
        continue
    body = json.load(open(os.path.join(d, name)))
    span = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["traceId"] = secrets.token_hex(16)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": os.environ["GATEWAY_AUTH"]})
    try:
        status = urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as e:
        status = e.code
    print(json.dumps({"cmd": "replay", "fixture": name, "status": status, "trace_id": span["traceId"]}))
PYEOF
}

run_replay() {
  say "replay: payloads a real Cloudflare AI Gateway exported on 2026-10-18, through otelcol.yaml"
  local pr="$P-replay" po="$P-replay-optin"
  start_collector "$pr" false FI "$FI_URL_FROM_DOCKER/v1/traces" || return 1
  expect "R1 real payloads, content off" 200 replay_fixtures
  sleep 8; save_logs replay
  verify "$pr" 2 --expect-type llm
  grep -q 'cf.aig.request' "$OUT/verify-$pr.txt" && note "span cf.aig.request stored as llm  $pr" || fail "no cf.aig.request span in $pr"
  scan "$pr" "" absent "prompt=Reply with exactly" "response_id=chatcmpl-" "reply=OK CFLIVE" "stream_chunks=streamed_data" || true
  scan "$pr" "" found "metadata_key=run_marker" || true
  start_collector "$po" true FI "$FI_URL_FROM_DOCKER/v1/traces" || return 1
  expect "R2 real payloads, content on" 200 replay_fixtures
  sleep 8; save_logs replay-optin
  verify "$po" 2 --expect-type llm
  scan "$po" "" found "prompt=Reply with exactly" "reply=OK CFLIVE" || true
  if grep -E '\- \[llm\].*in=[1-9][0-9]*B.*out=[1-9][0-9]*B' "$OUT/verify-$po.txt" >/dev/null 2>&1; then note "Input and Output panes filled with content on  $po"; else fail "Input or Output pane empty with content on  $po"; fi
}

case "$MODE" in
  direct) run_direct ;;
  collector) run_collector ;;
  replay) run_replay ;;
  all) run_direct; run_collector; run_replay ;;
  *) echo "usage: $0 [direct|collector|replay|all]"; exit 2 ;;
esac

say "summary"
cat "$SUMMARY"
[ "$FAILED" = 0 ] && echo "E2E OK" || { echo "E2E: one or more checks did not pass, see above"; exit 1; }
