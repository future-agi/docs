#!/usr/bin/env bash
# End-to-end run of the Azure APIM / AI Gateway recipe against a self-hosted Future AGI.
#
#   source <env with FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL>
#   PYTHON=/path/to/venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh [a|b|all]
#
# What is real and what is not:
#   real     traceAI-openai + fi-instrumentation-otel + openai (variant A client), the OpenTelemetry Collector container
#            running otelcol.yaml (variant B), the Future AGI collector and storage you point it at, and the model
#            calls behind variant A's spans (any OpenAI-compatible endpoint)
#   STAND-IN Azure API Management (apim_standin.py models policy/otlp-egress.policy.xml) and the Azure AI Gateway tier
#            (gateway_trace.py posts a SYNTHETIC trace shaped from Microsoft's release notes). No Azure subscription,
#            key, instance or code is involved, and nothing here was captured from Azure.
#
# Needs: Docker (variant B), a self-hosted Future AGI in Docker (the scan reads its Postgres and ClickHouse
#   containers; set FI_PG_CONTAINER / FI_CH_CONTAINER if named differently, or SKIP_SCAN=1), Python 3.12/3.13 venv with
#   `pip install -r requirements.txt`.
# Environment (defaults in brackets):
#   PYTHON [python3]  OUT [./evidence]  PROJECT [th8103-rest-azure-apim]  RUN_ID [empty]
#   OTELCOL_VERSION [0.162.0]  VERIFY [path to fi_verify.py, optional]  SKIP_SCAN=1  DOCKER_HOST_ALIAS [host.docker.internal]
# Content is never printed; evidence files can contain prompts and stay out of git.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
BASE="${PROJECT:-th8103-rest-azure-apim}"
P="$BASE${RUN_ID:+-$RUN_ID}"
OTELCOL_VERSION="${OTELCOL_VERSION:-0.162.0}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL (collector OTLP/HTTP base, e.g. http://localhost:4318)}"
: "${LLM_BASE_URL:?set LLM_BASE_URL}" "${LLM_API_KEY:?set LLM_API_KEY}" "${LLM_MODEL:?set LLM_MODEL}"
FI_BASE_URL="${FI_BASE_URL%/}"
TRACES_URL="$FI_BASE_URL/tracer/v1/traces"
CNAME="th8103-rest-azure-apim-otelcol"
APIM_PORT=18298; APIM_BAD_PORT=18299; GW_PORT=14298
HOST_ALIAS="${DOCKER_HOST_ALIAS:-host.docker.internal}"
SUB_KEY="sub-$("$PY" -c 'import secrets; print(secrets.token_hex(8))')"       # the APIM subscription key, invented per run
GW_TOKEN="gw-$("$PY" -c 'import secrets; print(secrets.token_hex(12))')"      # the bearer token the AI Gateway would send
mkdir -p "$OUT"
SUMMARY="$OUT/summary-$MODE.txt"; : > "$SUMMARY"
FAILED=0; PIDS=()

say() { printf '\n== %s\n' "$*"; }
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
fail() { note "CHECK FAILED: $*"; FAILED=1; }
uid() { "$PY" -c 'import secrets; print(secrets.token_hex(5).upper())'; }
cleanup() {
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null || true; done
  docker rm -f "$CNAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

verify() { # project min-spans [extra fi_verify args...]
  local project="$1" min="$2"; shift 2
  if [ -z "${VERIFY:-}" ]; then note "fi_verify skipped (VERIFY not set)  $project"; return; fi
  local try
  for try in 1 2 3 4; do  # the shared ClickHouse answers MEMORY_LIMIT_EXCEEDED under load; wait and retry
    "$PY" "$VERIFY" --project "$project" --wait 120 --min-spans "$min" --json "$OUT/spans-$project.json" "$@" >"$OUT/verify-$project.txt" 2>&1 || true
    grep -q '^clickhouse error' "$OUT/verify-$project.txt" || break
    sleep 45
  done
  sed -n '1,22p' "$OUT/verify-$project.txt" | cut -c1-200
  if grep -q '^PASS' "$OUT/verify-$project.txt"; then note "fi_verify PASS  $project"; else note "fi_verify FAIL  $project"; FAILED=1; fi
}

scan() { # project expect(found|absent) needle...
  local project="$1" expect="$2"; shift 2
  if [ "${SKIP_SCAN:-0}" = 1 ]; then note "scan skipped  $project"; return 0; fi
  local args=(--project "$project" --ignore-case --json "$OUT/scan-$project-$expect.json") n
  [ "$expect" = found ] && args+=(--expect-found)
  for n in "$@"; do args+=(--needle "$n"); done
  local rc try  # exit 2 = rows not stored yet, 3 = a table could not be read: neither is a verdict, so retry
  for try in 1 2 3 4 5; do
    "$PY" "$HERE/tools/scan_local_stack.py" "${args[@]}" | tee -a "$OUT/scan-$MODE.log" | cut -c1-240
    rc=${PIPESTATUS[0]}
    [ "$rc" -eq 2 ] || [ "$rc" -eq 3 ] || break
    sleep 30
  done
  if [ "$rc" -eq 0 ]; then note "scan OK ($expect)  $project"; else note "scan FAIL ($expect, exit $rc)  $project"; FAILED=1; fi
}

no_project() { # project: a rejected batch must leave no project behind
  local rc; "$PY" "$HERE/tools/scan_local_stack.py" --project "$1" --needle x >/dev/null 2>&1; rc=$?
  if [ "${SKIP_SCAN:-0}" = 1 ]; then return; fi
  if [ "$rc" -eq 2 ]; then note "OK   no project created for rejected batch ($1)"; else note "FAIL project exists for rejected batch ($1) rc=$rc"; FAILED=1; fi
}

expect_status() { # label want-status command...  (the command prints "HTTP <n> ...")
  local label="$1" want="$2"; shift 2
  local out got; out="$("$@" 2>&1)"; got="$(printf '%s\n' "$out" | sed -n 's/^HTTP \([0-9]*\).*/\1/p' | head -n 1)"
  if [ "$got" = "$want" ]; then note "OK   $label -> HTTP $got"; else note "FAIL $label -> HTTP ${got:-none}, expected $want"; FAILED=1; fi
}

versions() {
  "$PY" - <<'PYV'
import importlib.metadata as m, sys
print("versions: python", sys.version.split()[0], *(f"{n}=={m.version(n)}" for n in ["traceai-openai", "fi-instrumentation-otel", "openai", "opentelemetry-sdk"]))
PYV
}

start_standin() { # port apikey secretkey logfile
  FI_API_KEY="$2" FI_SECRET_KEY="$3" "$PY" "$HERE/apim_standin.py" --backend "$TRACES_URL" --port "$1" --subscription-key "$SUB_KEY" >"$4" 2>&1 &
  PIDS+=($!)
  for _ in $(seq 1 30); do curl -s -o /dev/null "http://127.0.0.1:$1/" && return 0; sleep 0.2; done
  fail "stand-in did not start on $1"
}

run_app() { # project marker [hide]
  local project="$1" marker="$2" hide="${3:-}"
  env -u FI_API_KEY -u FI_SECRET_KEY FI_BASE_URL="http://127.0.0.1:$APIM_PORT" FI_PROJECT_NAME="$project" APIM_SUBSCRIPTION_KEY="$SUB_KEY" \
    LLM_BASE_URL="$LLM_BASE_URL" LLM_API_KEY="$LLM_API_KEY" LLM_MODEL="$LLM_MODEL" \
    ${hide:+FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true} \
    "$PY" "$HERE/app.py" --prompt "find $marker" --system "system note $marker" | grep -E '^(RESULT|trace_id|session_id)' | sed 's/^\(RESULT [a-z]*\):.*/\1: <answer not printed>/'
}

variant_a() {
  say "variant A: APIM egress (STAND-IN for APIM) -> $TRACES_URL"
  versions | tee -a "$SUMMARY"
  start_standin "$APIM_PORT" "$FI_API_KEY" "$FI_SECRET_KEY" "$OUT/standin-a.log"
  local m_on="MARKA$(uid)" m_off="MARKA$(uid)" PA="$P-a" PH="$P-a-hidden"

  say "A1 real app, content on (traceAI default), marker $m_on"
  run_app "$PA" "$m_on" | tee -a "$SUMMARY"
  verify "$PA" 5 --expect-type agent --expect-type llm --expect-type tool
  scan "$PA" found "marker=$m_on"

  say "A2 real app, FI_HIDE_INPUTS/OUTPUTS=true, marker $m_off"
  run_app "$PH" "$m_off" hide | tee -a "$SUMMARY"
  verify "$PH" 5 --expect-type agent --expect-type llm
  scan "$PH" absent "marker=$m_off" "home=${HOME}" "user=$(id -un)" "host=$(hostname -s)"

  say "A3 negatives"
  local noproj="$P-a-neg"
  expect_status "missing APIM subscription key (stand-in answers, nothing forwarded)" 401 "$PY" "$HERE/gateway_trace.py" --url "http://127.0.0.1:$APIM_PORT/tracer/v1/traces" --project-name "$noproj"
  expect_status "wrong subscription key" 401 "$PY" "$HERE/gateway_trace.py" --url "http://127.0.0.1:$APIM_PORT/tracer/v1/traces" --header "Ocp-Apim-Subscription-Key=wrong" --project-name "$noproj"
  expect_status "unknown path" 404 "$PY" "$HERE/gateway_trace.py" --url "http://127.0.0.1:$APIM_PORT/v1/traces" --header "Ocp-Apim-Subscription-Key=$SUB_KEY" --project-name "$noproj"
  expect_status "no project_name on the resource (collector refuses)" 400 "$PY" "$HERE/gateway_trace.py" --url "http://127.0.0.1:$APIM_PORT/tracer/v1/traces" --header "Ocp-Apim-Subscription-Key=$SUB_KEY"
  expect_status "gzip body (collector refuses)" 400 "$PY" "$HERE/gateway_trace.py" --url "http://127.0.0.1:$APIM_PORT/tracer/v1/traces" --header "Ocp-Apim-Subscription-Key=$SUB_KEY" --project-name "$noproj" --compression gzip
  start_standin "$APIM_BAD_PORT" "wrong-api-key" "wrong-secret-key" "$OUT/standin-a-badkeys.log"
  expect_status "wrong Future AGI keys in the policy (collector 401, passed through)" 401 "$PY" "$HERE/gateway_trace.py" --url "http://127.0.0.1:$APIM_BAD_PORT/tracer/v1/traces" --header "Ocp-Apim-Subscription-Key=$SUB_KEY" --project-name "$noproj"
  no_project "$noproj"
}

collector_up() { # project capture(true|false)
  docker rm -f "$CNAME" >/dev/null 2>&1 || true
  docker run -d --name "$CNAME" --memory 256m -p "127.0.0.1:$GW_PORT:4318" -v "$HERE/otelcol.yaml:/etc/otelcol.yaml:ro" \
    -e GATEWAY_OTLP_TOKEN="$GW_TOKEN" -e FI_API_KEY -e FI_SECRET_KEY -e FI_PROJECT_NAME="$1" \
    -e FI_TRACES_URL="${FI_BASE_URL/localhost/$HOST_ALIAS}/v1/traces" -e FI_CAPTURE_CONTENT="$2" \
    "otel/opentelemetry-collector-contrib:$OTELCOL_VERSION" --config /etc/otelcol.yaml >/dev/null || { fail "docker run"; return 1; }
  for _ in $(seq 1 40); do curl -s -o /dev/null -X POST "http://127.0.0.1:$GW_PORT/v1/traces" && return 0; sleep 1; done
  fail "otelcol did not come up"; docker logs "$CNAME" 2>&1 | tail -5; return 1
}

variant_b() {
  say "variant B: AI Gateway tier (SYNTHETIC trace) -> otelcol $OTELCOL_VERSION -> $FI_BASE_URL"
  local m_off="MARKB$(uid)" m_on="MARKB$(uid)" PB="$P-b" PBON="$P-b-optin"
  local OID="00000000-0000-0000-0000-00000000bbbb"
  local url="http://127.0.0.1:$GW_PORT/v1/traces" auth="Authorization=Bearer $GW_TOKEN"

  say "B1 content off (default), marker $m_off, gzip body like a gateway may send"
  collector_up "$PB" false || return
  "$PY" "$HERE/gateway_trace.py" --url "$url" --header "$auth" --scenario both --marker "$m_off" --with-content --compression gzip | tee -a "$SUMMARY"
  verify "$PB" 7
  scan "$PB" absent "marker=$m_off" "oid=$OID" "home=${HOME}"

  say "B2 negatives"
  expect_status "wrong bearer token" 401 "$PY" "$HERE/gateway_trace.py" --url "$url" --header "Authorization=Bearer not-the-token"
  expect_status "no token" 401 "$PY" "$HERE/gateway_trace.py" --url "$url"
  note "logs path: HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $GW_TOKEN" -H 'Content-Type: application/x-protobuf' --data-binary '' "http://127.0.0.1:$GW_PORT/v1/logs") (a logs endpoint must not point here; expect 404)"

  say "B3 opt-in FI_CAPTURE_CONTENT=true, marker $m_on"
  collector_up "$PBON" true || return
  "$PY" "$HERE/gateway_trace.py" --url "$url" --header "$auth" --scenario both --marker "$m_on" --with-content | tee -a "$SUMMARY"
  verify "$PBON" 7
  scan "$PBON" found "marker=$m_on" "oid=$OID"
  docker rm -f "$CNAME" >/dev/null 2>&1
}

case "$MODE" in
  a) variant_a ;; b) variant_b ;; all) variant_a; variant_b ;;
  *) echo "usage: $0 [a|b|all]"; exit 2 ;;
esac
say "summary"; [ "$FAILED" -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED (see $SUMMARY)"
exit "$FAILED"
