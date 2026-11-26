#!/usr/bin/env bash
# End-to-end run of the Lambda tracing recipe against a Future AGI you can read back (self-hosted).
#
#   PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh [python|go|all]
#
# What is real: the OpenTelemetry SDK + OTLP/HTTP exporter (Python and Go), the example handlers and
# Future AGI. What is not: there is no AWS. The handler is called in-process the way the Lambda
# runtime calls it (one cold start, then warm invocations) with a stand-in context. No sam, no
# `aws lambda`, no LocalStack, no layer.
#
# Per language and project:  happy (3 invocations: API Gateway v2 with traceparent, direct, SQS)
#   failure (handler raises -> ERROR spans, flushed) | privacy (content off: unique marker, local
#   username, hostname, home path and "Traceback" absent from EVERY stored column; then the opt-in) |
#   nokeys (handler works, nothing exported, no project created) | deadend (collector unreachable:
#   the invocation still returns, bounded by the flush budget)
#
# Needs: FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL, VERIFY (fi_verify.py of the local stack),
# docker access to the stack's postgres/clickhouse containers (tools/scan_columns.py), go >= 1.26
# (GOTOOLCHAIN=auto downloads it). OUT defaults to ./evidence. RUN_ID defaults to MMDD-HHMM.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
BASE="${FI_PROJECT_PREFIX:-th8103-rest-aws-lambda}-${RUN_ID:-$(date +%m%d-%H%M)}"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}" "${VERIFY:?set VERIFY to fi_verify.py}"
export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"
mkdir -p "$OUT"; SUMMARY="$OUT/summary-$MODE.txt"; : >"$SUMMARY"; FAILED=0
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
fail() { note "FAIL  $*"; FAILED=1; }
ok() { note "ok    $*"; }

run_lang() { # python|go scenario project marker [env...]  -> runs the example, output in $OUT/run-*.txt
  local lang="$1" scen="$2" project="$3" marker="$4"; shift 4
  local log="$OUT/run-$lang-$scen.txt"
  if [ "$lang" = python ]; then
    ( cd "$HERE/python" && env "$@" FI_PROJECT_NAME="$project" "$PY" local_runner.py "$scen" ${marker:+--marker "$marker"} ) >"$log" 2>&1
  else
    ( cd "$HERE/go" && env "$@" FI_PROJECT_NAME="$project" "$GOBIN_E2E" "$scen" ${marker:-demo} ) >"$log" 2>&1
  fi
}
verify() { # project min-spans json   (retries: the shared ClickHouse can hit its memory cap)
  local i
  for i in 1 2 3 4; do
    "$PY" "$VERIFY" --project "$1" --wait 90 --min-spans "$2" --json "$3" --expect-type chain --expect-type tool >"$3.txt" 2>&1
    grep -q "clickhouse error" "$3.txt" || break
    sleep 30
  done
  grep -E "^(traces=|PASS|FAIL)" "$3.txt" | tr '\n' ' ' | tee -a "$SUMMARY"; echo | tee -a "$SUMMARY"
  grep -q '^PASS' "$3.txt"
}

lang_suite() {
  local lang="$1" tag="$2" p
  note; note "=== $lang ==="
  # happy
  p="$BASE-$tag-happy"
  run_lang "$lang" happy "$p" "" && grep -q "providers_built 1" "$OUT/run-$lang-happy.txt" && ok "$lang happy: 3 invocations returned, provider built once" || fail "$lang happy: run"
  verify "$p" 6 "$OUT/spans-$lang-happy.json" && "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-$lang-happy.json" happy | tee -a "$SUMMARY" || fail "$lang happy: trace shape"
  # failure
  p="$BASE-$tag-failure"
  run_lang "$lang" failure "$p" "" && grep -q "^raised" "$OUT/run-$lang-failure.txt" && ok "$lang failure: handler raised, warm invocation returned" || fail "$lang failure: run"
  verify "$p" 4 "$OUT/spans-$lang-failure.json" && "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-$lang-failure.json" failure | tee -a "$SUMMARY" || fail "$lang failure: trace shape"
  # privacy: content off (default), then opt-in
  local m u h hm
  m="tmp$("$PY" -c 'import secrets;print(secrets.token_hex(6))')"; u="$(id -un)"; h="$(hostname -s)"; hm="$HOME"
  p="$BASE-$tag-priv-off"
  run_lang "$lang" privacy "$p" "$m" && ok "$lang privacy (default): ran" || fail "$lang privacy off: run"
  verify "$p" 6 "$OUT/spans-$lang-priv-off.json" || fail "$lang privacy off: fi_verify"
  "$PY" "$HERE/tools/scan_columns.py" "$p" "marker=$m" "username=$u" "hostname=$h" "home=$hm" "traceback=Traceback" "gostack=goroutine" | tee "$OUT/scan-$lang-off.txt" | tee -a "$SUMMARY"
  grep -q "^project rows: [1-9]" "$OUT/scan-$lang-off.txt" || fail "$lang privacy off: no stored rows to scan (a scan of nothing proves nothing)"
  grep -E "^(marker|username|hostname|home|traceback|gostack):" "$OUT/scan-$lang-off.txt" | grep -qv "= 0$" && fail "$lang privacy off: something is stored" || ok "$lang privacy off: marker, username, hostname, home path, stack traces absent from every stored column"
  p="$BASE-$tag-priv-on"
  run_lang "$lang" privacy "$p" "$m" LAMBDA_TRACE_CAPTURE_CONTENT=true && ok "$lang privacy (opt-in): ran" || fail "$lang privacy on: run"
  verify "$p" 6 "$OUT/spans-$lang-priv-on.json" || fail "$lang privacy on: fi_verify"
  "$PY" "$HERE/tools/scan_columns.py" "$p" "marker=$m" "username=$u" "hostname=$h" "home=$hm" "traceback=Traceback" "gostack=goroutine" | tee "$OUT/scan-$lang-on.txt" | tee -a "$SUMMARY"
  grep -E "^marker:" "$OUT/scan-$lang-on.txt" | grep -q "= 0$" && fail "$lang opt-in: marker not stored" || ok "$lang opt-in: marker stored"
  grep -E "^(username|hostname|home|traceback|gostack):" "$OUT/scan-$lang-on.txt" | grep -qv "= 0$" && fail "$lang opt-in: user/host/path/stack stored" || ok "$lang opt-in: still no username, hostname, home path, stack trace"
  # nokeys
  p="$BASE-$tag-nokeys"
  run_lang "$lang" nokeys "$p" "" -u FI_API_KEY -u FI_SECRET_KEY && grep -c "^returned shipped" "$OUT/run-$lang-nokeys.txt" | grep -q 3 && ok "$lang nokeys: handler returned 3 results" || fail "$lang nokeys: run"
  sleep 5; "$PY" "$HERE/tools/scan_columns.py" "$p" | tee -a "$SUMMARY" | grep -q "project: absent" && ok "$lang nokeys: nothing exported, no project created" || fail "$lang nokeys: a project exists"
  # dead end
  local t0=$SECONDS
  run_lang "$lang" happy "$BASE-$tag-dead" "" FI_BASE_URL=http://127.0.0.1:9 && ok "$lang unreachable collector: 3 invocations returned in $((SECONDS - t0))s" || fail "$lang unreachable collector: run"
}

if [ "$MODE" = python ] || [ "$MODE" = all ]; then lang_suite python py; fi
if [ "$MODE" = go ] || [ "$MODE" = all ]; then
  GOBIN_E2E="$OUT/e2e-go"; (cd "$HERE/go" && go build -o "$GOBIN_E2E" ./cmd/e2e) || { fail "go build"; }
  lang_suite go go
fi
note; [ "$FAILED" = 0 ] && note "E2E PASS" || note "E2E FAIL"
exit "$FAILED"
