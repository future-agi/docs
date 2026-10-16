#!/usr/bin/env bash
# Real end-to-end: Kong AI Gateway (docker) -> OpenAI-compatible upstream, spans exported by Kong's own
# opentelemetry plugin to a local Future AGI stack. Four Kong boots:
#   1 content-off (+ tool-call and streaming)  2 content-on (log_payloads: true)  3 upstream-down  4 secrets via vault refs
# Required env: FI_API_KEY FI_SECRET_KEY FI_BASE_URL UPSTREAM_API_KEY  (see README)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}" "${UPSTREAM_API_KEY:?}"
# Kong runs in docker, so localhost on the host is host.docker.internal inside it
export FI_TRACES_ENDPOINT="${FI_TRACES_ENDPOINT:-$(echo "$FI_BASE_URL" | sed -E 's#//(localhost|127\.0\.0\.1)#//host.docker.internal#')/v1/traces}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-th8103-rest-kong-ai-gateway}"
export UPSTREAM_MODEL="${UPSTREAM_MODEL:-gpt-6-luna}"
export UPSTREAM_CHAT_URL="${UPSTREAM_CHAT_URL:-http://host.docker.internal:8317/v1/chat/completions}"
trap stop_kong EXIT
hex() { python3 -c "import uuid;print(uuid.uuid4().hex[:$1])"; }
SINCE=$(date -u +'%Y-%m-%d %H:%M:%S')
M_OFF="KONGMARK-OFF-$(hex 12)"; M_ON="KONGMARK-ON-$(hex 12)"
echo "$M_OFF $M_ON" > "$EVID/markers.txt"
EXTRA="/Users/someuser/secret-notes.txt someuser@example.com"
tp() { echo "00-$(hex 32)-$(hex 16)-01"; }
TP_OFF=$(tp); TP_ON=$(tp); TP_FAIL=$(tp); TP_TOOL=$(tp); TP_STREAM=$(tp); TP_VAULT=$(tp)
for t in "$TP_OFF" "$TP_ON" "$TP_FAIL" "$TP_TOOL" "$TP_STREAM" "$TP_VAULT"; do echo "$t" | cut -d- -f2; done > "$EVID/trace-ids.txt"

echo "== 1. content OFF (log_payloads: false) =="
export LOG_PAYLOADS=false; render "$EVID/kong.off.yml"; start_kong "$EVID/kong.off.yml"
chat "Reply with the single word ok. $M_OFF $EXTRA" "$TP_OFF" | tee "$EVID/resp.off.txt" | tail -1
curl -s -m 90 "http://127.0.0.1:$KONG_PROXY_PORT/chat" -H 'content-type: application/json' -H "traceparent: $TP_TOOL" \
  -d '{"messages":[{"role":"user","content":"Weather in Paris? Use the tool."}],"tools":[{"type":"function","function":{"name":"get_weather","description":"weather","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],"tool_choice":"required"}' \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print("tool request finish_reason:",d["choices"][0]["finish_reason"])'
curl -s -m 90 "http://127.0.0.1:$KONG_PROXY_PORT/chat" -H 'content-type: application/json' -H "traceparent: $TP_STREAM" \
  -d '{"stream":true,"stream_options":{"include_usage":true},"messages":[{"role":"user","content":"Count to three."}]}' | grep -c '^data:' | sed 's/^/streamed data lines: /'
# informational: does a query string reach the span? (Kong puts the full URL in http.url)
M_Q="QUERYMARK-$(hex 12)"
curl -s -m 90 -o /dev/null -w 'query-string request: HTTP %{http_code}\n' "http://127.0.0.1:$KONG_PROXY_PORT/chat?api_key=$M_Q" \
  -H 'content-type: application/json' -H 'Authorization: Bearer CALLERTOKEN-'"$M_Q" -d '{"messages":[{"role":"user","content":"hi"}]}'
echo "$M_Q" >> "$EVID/markers.txt"
sleep 8; assert_no_secrets_in_logs

echo "== 2. content ON (log_payloads: true) =="
export LOG_PAYLOADS=true; render "$EVID/kong.on.yml"; start_kong "$EVID/kong.on.yml"
chat "Reply with the single word ok. $M_ON" "$TP_ON" | tee "$EVID/resp.on.txt" | tail -1
sleep 8; assert_no_secrets_in_logs

UPSTREAM_CHAT_URL_OK=$UPSTREAM_CHAT_URL
echo "== 3. failure: upstream unreachable =="
export LOG_PAYLOADS=false UPSTREAM_CHAT_URL="http://host.docker.internal:1/v1/chat/completions"
render "$EVID/kong.fail.yml"; start_kong "$EVID/kong.fail.yml"
chat "This call must fail. KONGMARK-FAIL" "$TP_FAIL" | tee "$EVID/resp.fail.txt" | tail -1
sleep 8; assert_no_secrets_in_logs

echo "== 4. secrets by vault reference (headers = {vault://env/...}) =="
export LOG_PAYLOADS=false UPSTREAM_CHAT_URL="${UPSTREAM_CHAT_URL_OK}"
FI_API_KEY_REAL=$FI_API_KEY FI_SECRET_KEY_REAL=$FI_SECRET_KEY
FI_API_KEY='{vault://env/fi-api-key}' FI_SECRET_KEY='{vault://env/fi-secret-key}' render "$EVID/kong.vault.yml"
export FI_API_KEY=$FI_API_KEY_REAL FI_SECRET_KEY=$FI_SECRET_KEY_REAL
KONG_EXTRA_ARGS="-e KONG_VAULTS=env -e FI_API_KEY -e FI_SECRET_KEY" start_kong "$EVID/kong.vault.yml"
chat "vault reference run" "$TP_VAULT" | tail -1
echo "admin API shows header values as: $(curl -s "http://127.0.0.1:$KONG_ADMIN_PORT/plugins" | python3 -c 'import json,sys;print([p["config"]["headers"] for p in json.load(sys.stdin)["data"] if p["name"]=="opentelemetry"][0])')"
sleep 8; assert_no_secrets_in_logs
stop_kong

echo "== verify =="
for _ in 1 2 3 4 5 6; do   # shared local ClickHouse can hit its memory cap; retry
  python3 "${FI_VERIFY:-fi_verify.py}" --project "$FI_PROJECT_NAME" --wait 60 --min-spans 2 --expect-type llm --json "$EVID/spans.json" | tee "$EVID/fi_verify.txt" && break; sleep 30
done
python3 "$HERE/scan_privacy.py" --project "$FI_PROJECT_NAME" --since "$SINCE" \
  --absent "$M_OFF" --absent KONGMARK-FAIL --absent "someuser@example.com" --absent "secret-notes" --absent "/Users/someuser" \
  --absent "CALLERTOKEN-$M_Q" --present "$M_ON" | tee "$EVID/privacy-scan.txt"
echo "== informational: query string (known Kong behaviour, see page Limits) =="
python3 "$HERE/scan_privacy.py" --project "$FI_PROJECT_NAME" --since "$SINCE" --present "$M_Q" | tee "$EVID/query-string-scan.txt" || true
