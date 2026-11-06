#!/usr/bin/env bash
# Real end-to-end: the Gravitee APIM Gateway (Community Edition image, no licence) exports OTLP spans for
# v4 HTTP proxy APIs, through an OpenTelemetry Collector (otelcol.yaml), into a Future AGI project.
#
#   A  direct export Gateway -> Future AGI, project_name set with extraAttributes  (expected: rejected, 400)
#   B  content OFF: the shipped config (verbose off + redaction rules) via the Collector, incl. a failing
#      backend, an API with tracing off, an optional LLM request, and a request sent right before shutdown
#   C  content ON: Gateway verbose on (env override) + Verbose on the API, first with the Collector's content
#      switch off, then on (FI_CAPTURE_CONTENT=true, the opt-in); then a wrong Future AGI key on the Collector
#   D  wrong Collector token on the Gateway
# then checks every trace id it sent, runs fi_verify (if FI_VERIFY is set) and scans every stored column.
#
# Required env: FI_API_KEY FI_SECRET_KEY FI_BASE_URL
# Optional:     FI_PROJECT_NAME [gravitee-fi-e2e]  LLM_API_KEY (+ LLM_BASE_URL, LLM_MODEL) for the LLM request
#               FI_VERIFY=/path/to/fi_verify.py  PREFIX (container name prefix)  GRAVITEE_VERSION OTELCOL_VERSION
#               READY_TIMEOUT [600] seconds per readiness wait (per component: see lib.sh)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}"
# the Gateway and the Collector run in Docker: localhost on this machine is host.docker.internal inside them
FI_IN_DOCKER=$(echo "$FI_BASE_URL" | sed -E 's#//(localhost|127\.0\.0\.1)#//host.docker.internal#')
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-gravitee-fi-e2e}"
export FI_TRACES_URL="${FI_TRACES_URL:-$FI_IN_DOCKER/tracer/v1/traces}"
LLM_BASE_URL="${LLM_BASE_URL:-http://host.docker.internal:8317}"
LLM_MODEL="${LLM_MODEL:-gpt-6-luna}"
export GATEWAY_TOKEN="${GATEWAY_TOKEN:-$($PY -c 'import secrets;print(secrets.token_hex(16))')}"
REAL_FI_SECRET_KEY=$FI_SECRET_KEY
hex() { $PY -c "import uuid;print(uuid.uuid4().hex[:$1])"; }
tid() { echo "$1" | cut -d- -f2; }          # trace id of a traceparent
sid() { echo "$1" | cut -d- -f3; }          # caller span id of a traceparent
log() { echo "$*" | tee -a "$EVID/run.log"; }
trap 'kill "${BACKEND_PID:-}" 2>/dev/null || true; rm -f "$EVID/llm.hdr"; cleanup_all' EXIT
: > "$EVID/run.log"
: > "$EVID/readiness.txt"    # every wait in lib.sh appends the time its component took to become ready
SINCE=$(date -u +'%Y-%m-%d %H:%M:%S')
M_OFF="GRAVMARK-OFF-$(hex 10)"; M_V="GRAVMARK-VOFF-$(hex 10)"; M_ON="GRAVMARK-ON-$(hex 10)"; M_ON2="GRAVMARK-ON2-$(hex 10)"
EXTRA="/Users/someuser/secret-notes.txt someuser@example.com"
GW_HOSTS=()

# send <api> <marker> <traceparent>: POST with the marker in the body, query string and three headers
send() {
  curl -s -o /dev/null -w '%{http_code}' -m 60 -X POST \
    "http://127.0.0.1:$GW_PORT/$1/orders?q=$2-query&email=someuser@example.com" \
    -H "traceparent: $3" -H "Authorization: Bearer $2-auth" -H "X-Custom: $2-hdr" -H "Cookie: session=$2-cookie" \
    -H 'content-type: application/json' -d "{\"prompt\":\"$2-body $EXTRA\"}"
}
remember_gateway() {   # the Gateway container's hostname and IP must never be stored
  GW_HOSTS+=("$(docker inspect -f '{{.Config.Hostname}}' "$PREFIX-gw")")
  GW_HOSTS+=("$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$PREFIX-gw")")
}
gw_header() {  # gw_header <index> <name> <value>: exporter header via environment variables only
  export "gravitee_services_opentelemetry_exporter_headers_$1_name=$2" "gravitee_services_opentelemetry_exporter_headers_$1_value=$3"
}
clear_gw_headers() {
  unset gravitee_services_opentelemetry_exporter_headers_0_name gravitee_services_opentelemetry_exporter_headers_0_value
  unset gravitee_services_opentelemetry_exporter_headers_1_name gravitee_services_opentelemetry_exporter_headers_1_value
}

log "== setup: echo backend, MongoDB, Management API (creates + deploys the APIs, then stopped) =="
: > "$EVID/backend.log"
"$PY" "$HERE/echo_server.py" --port "$BACKEND_PORT" --log "$EVID/backend.log" & BACKEND_PID=$!
docker rm -f "$PREFIX-mongo" >/dev/null 2>&1 || true       # fresh repository every run
start_mongo
start_mapi
LLM_ARGS=(); [ -n "${LLM_API_KEY:-}" ] && LLM_ARGS=(--llm-backend "$LLM_BASE_URL")
"$PY" "$HERE/create_apis.py" --mapi "http://127.0.0.1:$MAPI_PORT" --backend "http://host.docker.internal:$BACKEND_PORT" "${LLM_ARGS[@]}" | tee -a "$EVID/run.log"
stop_mapi
log "versions: gateway graviteeio/apim-gateway:$GRAVITEE_VERSION, collector otel/opentelemetry-collector-contrib:$OTELCOL_VERSION, $MONGO_IMAGE"
TP_DIRECT=$(tp); TP_OFF=$(tp); TP_VOFF=$(tp); TP_FAIL=$(tp); TP_UNTRACED=$(tp); TP_LLM=$(tp); TP_FLUSH=$(tp)
TP_ONOFF=$(tp); TP_ON=$(tp); TP_ON2=$(tp); TP_BADKEY=$(tp); TP_BADTOKEN=$(tp)
M_ONOFF="GRAVMARK-ONOFF-$(hex 10)"

log "== A. direct export to Future AGI, project_name via extraAttributes (expected: rejected) =="
export gravitee_services_opentelemetry_exporter_endpoint="$FI_IN_DOCKER/tracer"   # env overrides gravitee.yml
render "$EVID/gw.direct.yml" --extra-attr "project_name=$FI_PROJECT_NAME" --extra-attr project_type=observe
gw_header 0 X-Api-Key "$FI_API_KEY"; gw_header 1 X-Secret-Key "$FI_SECRET_KEY"
start_gateway "$EVID/gw.direct.yml"; remember_gateway
log "direct request: HTTP $(send fi-echo GRAVMARK-DIRECT "$TP_DIRECT") trace $(tid "$TP_DIRECT")"
sleep 12
docker logs "$PREFIX-gw" 2>&1 | grep -i -E "export|status code|project" | grep -v -i "exporter.endpoint" | tail -3 | cut -c1-400 | tee "$EVID/direct-export.log" | tee -a "$EVID/run.log" || true
assert_no_secrets_in_logs | tee -a "$EVID/run.log"
stop_gateway; rm_gateway; clear_gw_headers; unset gravitee_services_opentelemetry_exporter_endpoint

log "== B. content OFF: shipped config (verbose: false, redaction rules) through the Collector =="
start_otelcol
render "$EVID/gw.off.yml"
gw_header 0 Authorization "Bearer $GATEWAY_TOKEN"
start_gateway "$EVID/gw.off.yml"; remember_gateway
log "fi-echo (content off):            HTTP $(send fi-echo "$M_OFF" "$TP_OFF") trace $(tid "$TP_OFF") caller span $(sid "$TP_OFF")"
log "fi-echo-verbose (API verbose on):  HTTP $(send fi-echo-verbose "$M_V" "$TP_VOFF") trace $(tid "$TP_VOFF")"
log "fi-down (backend unreachable):     HTTP $(send fi-down "$M_OFF" "$TP_FAIL") trace $(tid "$TP_FAIL")"
log "fi-untraced (API tracing off):     HTTP $(send fi-untraced "$M_OFF" "$TP_UNTRACED") trace $(tid "$TP_UNTRACED")"
# no caller traceparent: the Gateway starts a new root trace and forwards its traceparent to the backend
# (the response to the client carries no traceparent header, so read the trace id from the backend's log)
N_BACKEND=$(wc -l < "$EVID/backend.log")
ROOT_CODE=$(curl -s -D "$EVID/root.response-headers.txt" -o /dev/null -w '%{http_code}' -m 60 -X POST \
  "http://127.0.0.1:$GW_PORT/fi-echo/orders?q=$M_OFF-query" \
  -H 'content-type: application/json' -d "{\"prompt\":\"$M_OFF-body $EXTRA\"}")
ROOT_TRACE=$(tail -n +"$((N_BACKEND + 1))" "$EVID/backend.log" | "$PY" -c 'import json,sys
print(next((json.loads(l)["traceparent_trace_id"] or "" for l in sys.stdin if l.strip()), ""))')
log "fi-echo, no caller traceparent:    HTTP $ROOT_CODE new root trace ${ROOT_TRACE:-NONE} (trace id the backend got from the Gateway)"
log "  response traceparent header: $(grep -i -c '^traceparent:' "$EVID/root.response-headers.txt" || true)"
if [ -n "${LLM_API_KEY:-}" ]; then
  # the key goes in a private header file, never on a command line; removed on every exit path
  ( umask 077; printf 'Authorization: Bearer %s\n' "$LLM_API_KEY" > "$EVID/llm.hdr" )
  LLM_BODY="{\"model\":\"$LLM_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"What is the weather in Paris? $M_OFF-llm\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"get_weather\",\"description\":\"current weather\",\"parameters\":{\"type\":\"object\",\"properties\":{\"city\":{\"type\":\"string\"}},\"required\":[\"city\"]}}}],\"tool_choice\":\"required\"}"
  for attempt in 1 2 3; do
    code=$(curl -s -m 120 -o "$EVID/llm.resp.json" -w '%{http_code}' "http://127.0.0.1:$GW_PORT/fi-llm/v1/chat/completions" \
      -H @"$EVID/llm.hdr" -H "traceparent: $TP_LLM" -H 'content-type: application/json' -d "$LLM_BODY" || true)
    [ "$code" = 200 ] && break
    log "fi-llm attempt $attempt: HTTP $code (upstream busy?), retrying"; sleep 10
  done
  rm -f "$EVID/llm.hdr"
  "$PY" -c 'import json,sys
try:
    d=json.load(open(sys.argv[1])); c=d["choices"][0]
    print("fi-llm (LLM through the Gateway): model",d.get("model"),"finish_reason",c["finish_reason"],"tool",[t["function"]["name"] for t in c["message"].get("tool_calls") or []],"usage",d.get("usage",{}).get("total_tokens"))
except Exception as e:
    print("fi-llm: no usable response:", type(e).__name__)' "$EVID/llm.resp.json" | tee -a "$EVID/run.log"
  log "fi-llm HTTP $code trace $(tid "$TP_LLM")"
fi
sleep 8
log "fi-echo sent right before shutdown: HTTP $(send fi-echo "$M_OFF" "$TP_FLUSH") trace $(tid "$TP_FLUSH")"
stop_gateway                     # SIGTERM: the span sent just above must still be exported
assert_no_secrets_in_logs | tee -a "$EVID/run.log"
rm_gateway

log "== C. content ON: Gateway verbose (gravitee_services_opentelemetry_verbose=true) + Verbose on the API =="
export gravitee_services_opentelemetry_verbose=true
start_gateway "$EVID/gw.off.yml"; remember_gateway
log "fi-echo-verbose, Collector content switch off: HTTP $(send fi-echo-verbose "$M_ONOFF" "$TP_ONOFF") trace $(tid "$TP_ONOFF")"
sleep 8; stop_otelcol
export FI_CAPTURE_CONTENT=true; start_otelcol; unset FI_CAPTURE_CONTENT
log "fi-echo-verbose, FI_CAPTURE_CONTENT=true:      HTTP $(send fi-echo-verbose "$M_ON" "$TP_ON") trace $(tid "$TP_ON")"
log "fi-echo (API verbose off):        HTTP $(send fi-echo "$M_ON2" "$TP_ON2") trace $(tid "$TP_ON2")"
sleep 10
log "-- wrong Future AGI secret key on the Collector"
stop_otelcol
export FI_SECRET_KEY="wrong-$(hex 8)"; start_otelcol; export FI_SECRET_KEY=$REAL_FI_SECRET_KEY
log "fi-echo (Collector has bad key):  HTTP $(send fi-echo GRAVMARK-BADKEY "$TP_BADKEY") trace $(tid "$TP_BADKEY")"
sleep 10
docker logs "$PREFIX-otelcol" 2>&1 | grep -i -E "401|unauthor|permanent|error" | tail -2 | cut -c1-300 | tee "$EVID/badkey-collector.log" | tee -a "$EVID/run.log" || true
stop_gateway; rm_gateway; stop_otelcol; start_otelcol

log "== D. wrong Collector token on the Gateway =="
unset gravitee_services_opentelemetry_verbose
gw_header 0 Authorization "Bearer wrong-$(hex 8)"
start_gateway "$EVID/gw.off.yml"; remember_gateway
log "fi-echo (Gateway has bad token):  HTTP $(send fi-echo GRAVMARK-BADTOKEN "$TP_BADTOKEN") trace $(tid "$TP_BADTOKEN")"
sleep 12
docker logs "$PREFIX-gw" 2>&1 | grep -i -E "status code|401|export" | grep -v -i "exporter.endpoint" | tail -2 | cut -c1-300 | tee "$EVID/badtoken-gateway.log" | tee -a "$EVID/run.log" || true
assert_no_secrets_in_logs | tee -a "$EVID/run.log"
stop_gateway; rm_gateway; clear_gw_headers; stop_otelcol

log "== backend saw the caller's trace id (W3C traceparent forwarded) =="
grep -c "$(tid "$TP_OFF")" "$EVID/backend.log" | sed 's/^/backend requests carrying the fi-echo trace id: /' | tee -a "$EVID/run.log"
printf '%s\n' "$TP_DIRECT" "$TP_OFF" "root-trace-$ROOT_TRACE" "$TP_VOFF" "$TP_FAIL" "$TP_UNTRACED" "$TP_LLM" "$TP_FLUSH" "$TP_ONOFF" "$TP_ON" "$TP_ON2" "$TP_BADKEY" "$TP_BADTOKEN" > "$EVID/traceparents.txt"

log "== readiness (time each start took to pass its readiness probe; READY_TIMEOUT=${READY_TIMEOUT}s) =="
tee -a "$EVID/run.log" < "$EVID/readiness.txt"

log "== verify =="
set +e; RC=0
PRESENT=(--present "$(tid "$TP_OFF"):$(sid "$TP_OFF")" --present "$(tid "$TP_VOFF")" --present "$(tid "$TP_FAIL")"
         --present "$(tid "$TP_FLUSH")" --present "$(tid "$TP_ONOFF")" --present "$(tid "$TP_ON")" --present "$(tid "$TP_ON2")")
[ -n "${LLM_API_KEY:-}" ] && PRESENT+=(--present "$(tid "$TP_LLM")")
"$PY" "$HERE/check_traces.py" --project "$FI_PROJECT_NAME" "${PRESENT[@]}" \
  --absent "$(tid "$TP_DIRECT")" --absent "$(tid "$TP_UNTRACED")" --absent "$(tid "$TP_BADKEY")" --absent "$(tid "$TP_BADTOKEN")" \
  --root "${ROOT_TRACE:-none}" --error "$(tid "$TP_FAIL")" --json "$EVID/traces.json" | tee "$EVID/check-traces.txt" | tee -a "$EVID/run.log"
RC=$((RC + PIPESTATUS[0]))
if [ -n "${FI_VERIFY:-}" ]; then
  for _ in 1 2 3 4; do   # shared local ClickHouse can hit its memory cap; retry
    "$PY" "$FI_VERIFY" --project "$FI_PROJECT_NAME" --wait 60 --min-spans 2 --json "$EVID/spans.json" > "$EVID/fi_verify.txt" 2>&1 && break; sleep 30
  done
  grep -E "PASS|FAIL" "$EVID/fi_verify.txt" | tail -2 | tee -a "$EVID/run.log"
  grep -q "PASS" "$EVID/fi_verify.txt" || RC=$((RC + 1))
fi
ABSENT=()
for h in "${GW_HOSTS[@]}"; do ABSENT+=(--absent "$h"); done
"$PY" "$HERE/scan_privacy.py" --project "$FI_PROJECT_NAME" --since "$SINCE" \
  --absent "$M_OFF" --absent "$M_V" --absent "$M_ONOFF" --absent "$M_ON2" --absent "$M_ON-body" --absent "$M_ON-query" \
  --absent "$M_ON-auth" --absent "$M_ON-cookie" --absent "someuser@example.com" --absent "/Users/someuser" --absent "secret-notes" \
  --absent "Connection refused" --absent "GRAVMARK-DIRECT" --absent "GRAVMARK-BADKEY" --absent "GRAVMARK-BADTOKEN" "${ABSENT[@]}" \
  --absent-env FI_API_KEY --absent-env FI_SECRET_KEY --absent-env GATEWAY_TOKEN --absent-env LLM_API_KEY \
  --present "$M_ON-hdr" --present "POST /fi-echo" | tee "$EVID/privacy-scan.txt" | tee -a "$EVID/run.log"
RC=$((RC + PIPESTATUS[0]))
log "E2E $([ "$RC" = 0 ] && echo PASS || echo FAIL)"
exit "$RC"
