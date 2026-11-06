#!/usr/bin/env bash
# End-to-end run of the Cloudflare Agents recipe against a self-hosted Future AGI you can read back.
#
#   source <env with FI_API_KEY FI_SECRET_KEY FI_BASE_URL OPENAI_API_KEY [OPENAI_BASE_URL MODEL]>
#   VERIFY=/path/to/fi_verify.py ./run_e2e.sh
#
# What is real:
#   the Worker in src/index.ts on workerd (`wrangler dev`, local mode), `agents` (Agent + wrapAISDK), the AI SDK,
#   a real model call per step (any OpenAI-compatible endpoint), the spans and log lines workerd records, the
#   OpenTelemetry Collector container running otelcol.yaml unchanged, and Future AGI.
# What is a STANDIN:
#   Cloudflare's OTLP traces destination. `wrangler dev` has no destinations, so standin/destination.mjs reads what
#   workerd captured (Local Explorer store) and POSTs it to the collector as OTLP/HTTP JSON with the bearer header a
#   destination would carry. No Cloudflare account, login, deploy or tunnel is involved.
#
# Scenarios: happy turn with a tool | tool throws | model call fails | collector auth (no/wrong token) | content off
# (unique markers, every stored column scanned) | guard (STORE_MESSAGES/STORE_TOOLS on, collector default) | content on
# (STORE_MESSAGES/STORE_TOOLS + FI_CAPTURE_CONTENT) | no cross-project data (no leg's marker in another leg's project).
#
# Needs: Docker (collector + the stack's postgres/clickhouse containers for the scans), node >= 20, python3, curl,
# and `npm install` in this directory. Evidence goes to ./evidence (never commit it: it can contain prompts).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
PY="${PYTHON:-python3}"; OUT="${OUT:-$HERE/evidence}"; PORT="${PORT:-8799}"; CPORT="${COLLECTOR_PORT:-14480}"
BASE="${PROJECT:-th8103-rest-cloudflare-agents}"
OTELCOL_IMAGE="otel/opentelemetry-collector-contrib:${OTELCOL_VERSION:-0.162.0}"
CNAME="${COLLECTOR_CONTAINER:-th8103-rest-cloudflare-agents-otelcol}"
MODEL="${MODEL:-gpt-6-luna}"
BAD_MODEL="no-such-model-th8259"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}" "${OPENAI_API_KEY:?}"
# The collector runs in Docker: point it at the host's Future AGI.
FI_TRACES_URL="${FI_TRACES_URL:-$(printf '%s' "$FI_BASE_URL" | sed -e 's#//localhost#//host.docker.internal#' -e 's#//127.0.0.1#//host.docker.internal#')/v1/traces}"
CF_DESTINATION_TOKEN="cfd-$("$PY" -c 'import secrets;print(secrets.token_hex(16))')"   # invented per run, never printed
export FI_API_KEY FI_SECRET_KEY FI_TRACES_URL CF_DESTINATION_TOKEN
mkdir -p "$OUT"; SUMMARY="$OUT/summary.txt"; : >"$SUMMARY"; FAILED=0
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
ok() { note "ok    $*"; }
fail() { note "FAIL  $*"; FAILED=1; }
WPID=""; XDG="$(mktemp -d)"
stop_worker() { if [ -n "$WPID" ]; then pkill -P "$WPID" 2>/dev/null; kill "$WPID" 2>/dev/null; wait "$WPID" 2>/dev/null; fi; WPID=""
  lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null; rm -f .dev.vars; }
stop_collector() { docker logs "$CNAME" >>"$OUT/collector.log" 2>&1 || true; docker rm -f "$CNAME" >/dev/null 2>&1 || true; }
trap 'stop_worker; stop_collector; rm -rf "$XDG"' EXIT

# collector <project> <capture true|false>
collector() {
  stop_collector
  FI_PROJECT_NAME="$1" FI_CAPTURE_CONTENT="$2" docker run -d --name "$CNAME" --memory 256m \
    -p "127.0.0.1:$CPORT:4318" -e CF_DESTINATION_TOKEN -e FI_API_KEY -e FI_SECRET_KEY -e FI_TRACES_URL \
    -e FI_PROJECT_NAME -e FI_CAPTURE_CONTENT -v "$HERE/otelcol.yaml:/etc/otelcol-contrib/config.yaml:ro" \
    "$OTELCOL_IMAGE" >/dev/null || return 1
  local i code
  for i in $(seq 1 40); do  # ready = the receiver answers (401 without the token)
    code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$CPORT/v1/traces" -H 'content-type: application/json' -d '{}')"
    [ "$code" = 401 ] && return 0; sleep 1
  done
  docker logs "$CNAME" 2>&1 | tail -5 >>"$OUT/collector.log"; return 1
}

# worker <label> [VAR=value ...]   start workerd; vars go to a throw-away .dev.vars (mode 600), never on a command line
worker() {
  local label="$1"; shift
  stop_worker
  ( umask 077
    { echo "OPENAI_API_KEY=$OPENAI_API_KEY"; [ -n "${OPENAI_BASE_URL:-}" ] && echo "OPENAI_BASE_URL=$OPENAI_BASE_URL"; echo "MODEL=$MODEL"
      :; } >.dev.vars
    for kv in "$@"; do grep -v "^${kv%%=*}=" .dev.vars >.dev.vars.tmp; mv .dev.vars.tmp .dev.vars; echo "$kv" >>.dev.vars; done )
  XDG_CONFIG_HOME="$XDG" WRANGLER_SEND_METRICS=false CI=true NO_COLOR=1 \
    npx --no-install wrangler dev --local --port "$PORT" --ip 127.0.0.1 >"$OUT/wrangler-$label.log" 2>&1 &
  WPID=$!
  local i; for i in $(seq 1 90); do grep -q "Ready on" "$OUT/wrangler-$label.log" 2>/dev/null && return 0; sleep 1; done
  return 1
}
clear_store() { curl -s -X POST "http://127.0.0.1:$PORT/cdn-cgi/local/explorer/api/local/observability/clear" >/dev/null; }
# turn <instance> <question>   one HTTP turn to the Agent instance; prints the HTTP status and the JSON answer
turn() {
  local body; body="$("$PY" -c 'import json,sys;print(json.dumps({"question":sys.argv[1]}))' "$2")"
  curl -s -m 120 -w ' HTTP %{http_code}' -X POST "http://127.0.0.1:$PORT/agents/weather-agent/$1" \
    -H 'content-type: application/json' -d "$body"
}
# export_spans <label>   STANDIN destination: workerd's spans -> collector. Sets TRACE_IDS.
export_spans() {
  sleep 2  # let the last invocation's spans end
  node standin/destination.mjs --explorer "http://127.0.0.1:$PORT" --endpoint "http://127.0.0.1:$CPORT/v1/traces" \
    --dump "$OUT/rows-$1.json" >"$OUT/export-$1.txt" 2>&1 || { fail "$1: stand-in export"; tail -3 "$OUT/export-$1.txt"; }
  TRACE_IDS="$(tail -1 "$OUT/export-$1.txt" | "$PY" -c 'import json,sys;print(",".join(json.load(sys.stdin)["trace_ids"]))' 2>/dev/null)"
  note "$1: $(tail -1 "$OUT/export-$1.txt" | "$PY" -c 'import json,sys;d=json.load(sys.stdin);print("workerd spans",d["rows"],"log lines",d["logs"],"posted",d["exported_spans"],"traces",d["trace_ids"])' 2>/dev/null)"
}
verify() { # project out trace-id,trace-id,...   waits until every listed trace is stored
  [ -n "${VERIFY:-}" ] || { note "fi_verify skipped (VERIFY not set)"; return 0; }
  local want n i missing="(ClickHouse busy, not checked)"
  want="$(printf '%s' "$3" | tr ',' '\n' | grep -c .)"; n=$((want * 8))
  for i in 1 2 3 4 5 6; do
    "$PY" "$VERIFY" --project "$1" --wait 120 --min-spans "$n" --json "$2" \
      --expect-type agent --expect-type llm --expect-type tool --expect-type chain >"$2.txt" 2>&1
    if grep -qi "clickhouse error\|memory limit" "$2.txt"; then note "(info) ClickHouse busy, retry $i"; sleep 40; continue; fi
    missing="$("$PY" -c 'import json,sys;got={s["trace_id"].replace("-","") for s in json.load(open(sys.argv[1]))};print(",".join(t for t in sys.argv[2].split(",") if t and t not in got))' "$2" "$3" 2>/dev/null)"
    [ -z "$missing" ] && break
    note "(info) not stored yet: $missing (retry $i)"; sleep 20
  done
  [ -n "$missing" ] && note "MISSING traces in $1: $missing"
  note "fi_verify $1: $(grep -E '^(traces=|PASS|FAIL)' "$2.txt" | tr '\n' ' ')"
  grep -q '^PASS' "$2.txt" && [ -z "$missing" ]
}
VERS="$(node -e 'const v=p=>require("./node_modules/"+p+"/package.json").version;console.log(["agents","ai","@ai-sdk/openai","zod","wrangler","workerd"].map(p=>p+" "+v(p)).join(", "))')"
note "versions: $VERS, node $(node -v), collector $OTELCOL_IMAGE, model $MODEL"
RUN="$(date +%m%d%H%M%S)"

# --- 1. happy turn, then a turn whose tool throws (project $BASE) ---
collector "$BASE" false || fail "collector did not start"
worker main || fail "workerd did not start"
clear_store
note "happy turn: $(turn "conv-$RUN-a" "What is the weather in Lisbon?")"
export_spans happy; HAPPY="$TRACE_IDS"
clear_store
note "tool-error turn: $(turn "conv-$RUN-b" "What is the weather in Atlantis?")"
export_spans tool-error; TOOLERR="$TRACE_IDS"
# --- 2. the model call fails (wrong model name) ---
worker model-error "MODEL=$BAD_MODEL" || fail "workerd did not start"
clear_store
note "model-error turn: $(turn "conv-$RUN-c" "What is the weather in Porto?")"
export_spans model-error; MODELERR="$TRACE_IDS"
if verify "$BASE" "$OUT/spans-main.json" "$HAPPY,$TOOLERR,$MODELERR"; then ok "fi_verify PASS ($BASE)"; else fail "fi_verify ($BASE)"; fi
"$PY" tools/check_trace.py "$OUT/spans-main.json" happy --model "$MODEL" --traces "$HAPPY" | tee -a "$SUMMARY" | grep -q '^OK' || fail "happy: trace shape"
"$PY" tools/check_trace.py "$OUT/spans-main.json" tool-error --model "$MODEL" --traces "$TOOLERR" | tee -a "$SUMMARY" | grep -q '^OK' || fail "tool-error: trace shape"
"$PY" tools/check_trace.py "$OUT/spans-main.json" model-error --model "$BAD_MODEL" --traces "$MODELERR" | tee -a "$SUMMARY" | grep -q '^OK' || fail "model-error: trace shape"

# --- 3. collector auth ---
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$CPORT/v1/traces" -H 'content-type: application/json' -d '{"resourceSpans":[]}')"
[ "$code" = 401 ] && ok "collector: no token -> 401" || fail "collector: no token -> $code"
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$CPORT/v1/traces" -H 'content-type: application/json' -H 'authorization: Bearer not-the-token' -d '{"resourceSpans":[]}')"
[ "$code" = 401 ] && ok "collector: wrong token -> 401" || fail "collector: wrong token -> $code"

# --- 4. privacy: content off (the default on both sides), then the documented opt-in ---
hex() { "$PY" -c 'import secrets;print(secrets.token_hex(6))'; }
MOFF="cfagoff$(hex)"; MGUARD="cfagguard$(hex)"; MON="cfagon$(hex)"   # content markers, one per leg
E="mail$("$PY" -c 'import secrets;print(secrets.token_hex(5))')"   # e-mail-shaped agent instance name
EMAIL="$E@example.com"
U="$(id -un)"; H="$(hostname -s)"
scan() { # project out marker
  "$PY" tools/scan_columns.py "$1" "marker=$3" "email_local=$E" "username=$U" "hostname=$H" "home=$HOME" "cwd=$HERE" \
    "traceback=Traceback" "jsframe=.ts:" "fi_api_key=$FI_API_KEY" "fi_secret=$FI_SECRET_KEY" "model_key=$OPENAI_API_KEY" \
    "dest_token=$CF_DESTINATION_TOKEN" >"$2" 2>&1
  sed -n '1p' "$2" | tee -a "$SUMMARY"
}
privacy_turns() { # marker
  clear_store
  note "privacy turn 1: $(turn "$EMAIL" "What is the weather in $1ville? Repeat the city name in your answer.")"
  note "privacy turn 2: $(turn "$EMAIL" "And in Atlantis-$1 ?")"
}
P_OFF="$BASE-privacy-off"
collector "$P_OFF" false || fail "collector did not start"
worker privacy-off || fail "workerd did not start"
privacy_turns "$MOFF"; export_spans privacy-off; PRIVOFF="$TRACE_IDS"
"$PY" -c 'import json,sys;r=open(sys.argv[1]).read();print("pre-collector (what the Worker emitted): marker occurrences",r.count(sys.argv[2]),"| e-mail local part occurrences",r.count(sys.argv[3]))' \
  "$OUT/rows-privacy-off.json" "$MOFF" "$E" | tee -a "$SUMMARY"
if verify "$P_OFF" "$OUT/spans-privacy-off.json" "$PRIVOFF"; then ok "fi_verify PASS ($P_OFF)"; else fail "fi_verify ($P_OFF)"; fi
scan "$P_OFF" "$OUT/scan-off.txt" "$MOFF"
if ! grep -q "^project rows: [1-9]" "$OUT/scan-off.txt"; then fail "privacy-off: no stored rows to scan (a scan of nothing proves nothing)"
elif grep -E "^[a-z_]+: rows containing it" "$OUT/scan-off.txt" | grep -qv "= 0$"; then fail "privacy-off: something is stored: $(grep -v '= 0$' "$OUT/scan-off.txt" | tail -n +2 | cut -d'[' -f1 | tr '\n' ';')"
else ok "privacy-off: marker, e-mail, username, hostname, home and cwd paths, stack frames and all keys absent from every stored column"; fi

# Guard: Cloudflare's payload switches on (as for its own session replay), collector default. Content reaches the
# collector and must stop there.
P_GUARD="$BASE-guard"
collector "$P_GUARD" false || fail "collector did not start"
worker guard STORE_MESSAGES=true STORE_TOOLS=true || fail "workerd did not start"
privacy_turns "$MGUARD"; export_spans guard; GUARD="$TRACE_IDS"
SENT="$("$PY" -c 'import sys;print(open(sys.argv[1]).read().count(sys.argv[2]))' "$OUT/rows-guard.json" "$MGUARD")"
note "guard: marker occurrences in what the Worker emitted (sent to the collector): $SENT"
[ "${SENT:-0}" -gt 0 ] || fail "guard: the Worker did not record payloads, so the guard was not exercised"
if verify "$P_GUARD" "$OUT/spans-guard.json" "$GUARD"; then ok "fi_verify PASS ($P_GUARD)"; else fail "fi_verify ($P_GUARD)"; fi
scan "$P_GUARD" "$OUT/scan-guard.txt" "$MGUARD"
if ! grep -q "^project rows: [1-9]" "$OUT/scan-guard.txt"; then fail "guard: no stored rows to scan (a scan of nothing proves nothing)"
elif grep -E "^[a-z_]+: rows containing it" "$OUT/scan-guard.txt" | grep -qv "= 0$"; then fail "guard: something is stored: $(grep -v '= 0$' "$OUT/scan-guard.txt" | tail -n +2 | cut -d'[' -f1 | tr '\n' ';')"
else ok "guard: payloads recorded by the Worker were not stored (marker, e-mail, identity, paths, keys all 0)"; fi

P_ON="$BASE-optin"
collector "$P_ON" true || fail "collector did not start"
worker optin STORE_MESSAGES=true STORE_TOOLS=true || fail "workerd did not start"
privacy_turns "$MON"; export_spans optin; OPTIN="$TRACE_IDS"
if verify "$P_ON" "$OUT/spans-optin.json" "$OPTIN"; then ok "fi_verify PASS ($P_ON)"; else fail "fi_verify ($P_ON)"; fi
scan "$P_ON" "$OUT/scan-on.txt" "$MON"
grep -E "^marker:" "$OUT/scan-on.txt" | grep -q "= 0$" && fail "opt-in: marker not stored" || ok "opt-in: marker stored ($(grep -E '^marker:' "$OUT/scan-on.txt" | cut -d'[' -f2 | tr -d ']'))"
if grep -E "^(email_local|username|hostname|home|cwd|traceback|jsframe|fi_api_key|fi_secret|model_key|dest_token):" "$OUT/scan-on.txt" | grep -qv "= 0$"; then fail "opt-in: identity/path/key stored"
else ok "opt-in: still no e-mail, username, hostname, paths, stack frames or keys"; fi
"$PY" - "$OUT/spans-optin.json" <<'PYEOF' | tee -a "$SUMMARY"
import json,sys
s=json.load(open(sys.argv[1]))
llm=[x for x in s if x["observation_type"]=="llm"]; tool=[x for x in s if x["observation_type"]=="tool"]
print("opt-in Input/Output filled: llm", sum(1 for x in llm if x["input_length"] and x["output_length"]), "/", len(llm),
      "| tool", sum(1 for x in tool if x["input_length"]), "/", len(tool))
PYEOF
# --- 5. no cross-project data: each leg's marker is absent from the other leg's project ---
"$PY" tools/scan_columns.py "$P_OFF" "optin_marker=$MON" "guard_marker=$MGUARD" >"$OUT/scan-cross-off.txt" 2>&1
"$PY" tools/scan_columns.py "$P_GUARD" "optin_marker=$MON" "off_marker=$MOFF" >"$OUT/scan-cross-guard.txt" 2>&1
"$PY" tools/scan_columns.py "$P_ON" "off_marker=$MOFF" "guard_marker=$MGUARD" >"$OUT/scan-cross-on.txt" 2>&1
if grep -h -E "^(optin_marker|off_marker|guard_marker):" "$OUT"/scan-cross-*.txt | grep -qv "= 0$"; then fail "cross-project: a marker reached another project"
else ok "cross-project: no leg's marker appears in another leg's project ($P_OFF, $P_GUARD, $P_ON)"; fi

stop_worker; stop_collector
note; [ "$FAILED" = 0 ] && note "E2E PASS" || note "E2E FAIL"
exit "$FAILED"
