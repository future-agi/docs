#!/usr/bin/env bash
# End-to-end run of the Workers AI tracing recipe against a Future AGI you can read back (self-hosted).
#
#   VERIFY=/path/to/fi_verify.py ./run_e2e.sh
#
# What is real: workerd (inside `wrangler dev --local`), the example handler and tracer, the OTLP/JSON export from the
# isolate, and Future AGI. What is a STANDIN: env.AI. src/e2e-entry.ts replaces it with a stub whose run() calls an
# OpenAI-compatible endpoint (CLIPROXY_OPENAI_BASE_URL, model gpt-6-luna) and returns {response, usage}. Cloudflare is never
# contacted: no login, no `wrangler deploy`, no Workers AI call, no Cloudflare API call.
#
# Scenarios (one local workerd per scenario, each its own Future AGI project):
#   happy (2 requests) | failure (the AI call throws -> 502, ERROR spans, flushed) |
#   privacy-off (unique marker in prompt + response + error text, scanned across ALL stored columns) | privacy-on (opt-in) |
#   nokeys (works, nothing exported, no project) | deadend (collector unreachable: the request still returns, bounded)
#
# Needs: FI_API_KEY FI_SECRET_KEY FI_BASE_URL CLIPROXY_API_KEY CLIPROXY_OPENAI_BASE_URL (source e2e/env.sh), VERIFY,
# docker access to the stack's postgres/clickhouse containers (tools/scan_columns.py), node >= 20.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
PY="${PYTHON:-python3}"; OUT="${OUT:-$PWD/evidence}"; PORT="${PORT:-8788}"
BASE="${FI_PROJECT_PREFIX:-th8103-rest-cloudflare-workers-ai}-${RUN_ID:-$(date +%m%d-%H%M)}"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}" "${VERIFY:?set VERIFY to fi_verify.py}" "${CLIPROXY_API_KEY:?}" "${CLIPROXY_OPENAI_BASE_URL:?}"
mkdir -p "$OUT"; SUMMARY="$OUT/summary.txt"; : >"$SUMMARY"; FAILED=0
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
fail() { note "FAIL  $*"; FAILED=1; }
ok() { note "ok    $*"; }
WPID=""; CFG="$(mktemp -d)"
stop_worker() { [ -n "$WPID" ] && { pkill -P "$WPID" 2>/dev/null; kill "$WPID" 2>/dev/null; wait "$WPID" 2>/dev/null; }; WPID=""; rm -f .dev.vars; }
trap 'stop_worker; rm -rf "$CFG"' EXIT

# serve <project> [VAR=value ...]   start workerd; vars go to a throw-away .dev.vars (mode 600), never on a command line
serve() {
  local project="$1"; shift
  stop_worker
  ( umask 077
    { echo "FI_API_KEY=$FI_API_KEY"; echo "FI_SECRET_KEY=$FI_SECRET_KEY"; echo "FI_BASE_URL=$FI_BASE_URL"
      echo "FI_PROJECT_NAME=$project"
      echo "STANDIN_BASE_URL=$CLIPROXY_OPENAI_BASE_URL"; echo "STANDIN_API_KEY=$CLIPROXY_API_KEY"; echo "STANDIN_MODEL=${STANDIN_MODEL:-gpt-6-luna}"
      :; } >.dev.vars
    for kv in "$@"; do case "$kv" in UNSET_KEYS=*) ;; *) sed -i.bak "/^${kv%%=*}=/d" .dev.vars; rm -f .dev.vars.bak; echo "$kv" >>.dev.vars;; esac; done )
  # `-` prefix on a var name removes it: used by the nokeys scenario
  if printf '%s\n' "$@" | grep -q '^UNSET_KEYS=1'; then sed -i.bak '/^FI_API_KEY=/d;/^FI_SECRET_KEY=/d' .dev.vars; rm -f .dev.vars.bak; fi
  XDG_CONFIG_HOME="$CFG" WRANGLER_SEND_METRICS=false CI=true NO_COLOR=1 \
    npx --no-install wrangler dev --local --config wrangler.e2e.jsonc --port "$PORT" --ip 127.0.0.1 >"$OUT/wrangler-$project.log" 2>&1 &
  WPID=$!
  # readiness from the log, not by sending a request (a request would create a trace)
  for _ in $(seq 1 90); do grep -q "Ready on" "$OUT/wrangler-$project.log" 2>/dev/null && return 0; sleep 1; done
  return 1
}
ask() { # prompt  -> prints "status<TAB>seconds"
  curl -s -o "$OUT/last-body.txt" -w '%{http_code}\t%{time_total}\n' -X POST "http://127.0.0.1:$PORT/chat?token=query-secret-$RANDOM" \
    -H 'content-type: application/json' -d "$(printf '{"prompt":%s}' "$("$PY" -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1")")" --max-time 60
}
verify() { # project min-spans json
  local i
  for i in 1 2 3 4; do
    "$PY" "$VERIFY" --project "$1" --wait 90 --min-spans "$2" --json "$3" --expect-type llm --expect-type chain >"$3.txt" 2>&1
    grep -q "clickhouse error" "$3.txt" || break; sleep 30
  done
  grep -E "^(traces=|PASS|FAIL)" "$3.txt" | tr '\n' ' ' | tee -a "$SUMMARY"; echo | tee -a "$SUMMARY"
  grep -q '^PASS' "$3.txt"
}
VERS="$(node -e 'console.log(require("./node_modules/wrangler/package.json").version, require("./node_modules/workerd/package.json").version)')"
note "wrangler/workerd: $VERS   node: $(node -v)   run: $BASE"

# happy
P="$BASE-happy"; serve "$P" || fail "happy: workerd did not start"
r1="$(ask 'Reply with the single word: pong')"; r2="$(ask 'Name one primary colour in one word.')"
note "requests: $r1 | $r2"
case "$r1$r2" in 200*200*) ok "happy: both requests returned 200";; *) fail "happy: statuses $r1 $r2";; esac
verify "$P" 4 "$OUT/spans-happy.json" && "$PY" tools/check_trace.py "$OUT/spans-happy.json" happy | tee -a "$SUMMARY" || fail "happy: trace shape"

# failure
P="$BASE-failure"; serve "$P" || fail "failure: workerd did not start"
r="$(ask 'please __fail__ now')"; note "request: $r"
case "$r" in 502*) ok "failure: 502 returned";; *) fail "failure: status $r";; esac
r="$(ask 'Reply with the single word: pong')"; case "$r" in 200*) ok "failure: next request fine";; *) fail "failure: next request $r";; esac
verify "$P" 4 "$OUT/spans-failure.json" || true
"$PY" - "$OUT/spans-failure.json" <<'PYEOF' | tee -a "$SUMMARY"
import json,sys
s=json.load(open(sys.argv[1])); err=[x for x in s if x["status"]=="ERROR"]
print("failure spans:", len(s), "ERROR:", sorted(x["name"] for x in err), "ok-traces:", len({x["trace_id"] for x in s})-len({x["trace_id"] for x in err}))
PYEOF
"$PY" tools/check_trace.py "$OUT/spans-failure.json" failure | tee -a "$SUMMARY" || fail "failure: trace shape"

# privacy: unique marker in the prompt (the stub echoes it in its error text and the model may echo it back)
M="tmp$("$PY" -c 'import secrets;print(secrets.token_hex(6))')"; U="$(id -un)"; H="$(hostname -s)"; HM="$HOME"
scan() { "$PY" tools/scan_columns.py "$1" "marker=$M" "username=$U" "hostname=$H" "home=$HM" "traceback=Traceback" "atline= at " "stack=.ts:" | tee "$2" | tee -a "$SUMMARY"; }
PROMPT_OK="Repeat this token exactly once and nothing else: $M"
PROMPT_FAIL="__fail__ $M"
P="$BASE-priv-off"; serve "$P" || fail "privacy-off: workerd did not start"
ask "$PROMPT_OK" >/dev/null; ask "$PROMPT_FAIL" >/dev/null
grep -q "$M" "$OUT/last-body.txt" && fail "privacy-off: marker in the HTTP error body"  # the 502 body is generic
verify "$P" 4 "$OUT/spans-priv-off.json" || fail "privacy-off: fi_verify"
scan "$P" "$OUT/scan-off.txt"
grep -q "^project rows: [1-9]" "$OUT/scan-off.txt" || fail "privacy-off: no stored rows to scan (a scan of nothing proves nothing)"
grep -E "^(marker|username|hostname|home|traceback|atline|stack):" "$OUT/scan-off.txt" | grep -qv "= 0$" && fail "privacy-off: something is stored" || ok "privacy-off: marker, username, hostname, home path, stack frames absent from every stored column"
P="$BASE-priv-on"; serve "$P" FI_CAPTURE_CONTENT=true || fail "privacy-on: workerd did not start"
ask "$PROMPT_OK" >/dev/null; ask "$PROMPT_FAIL" >/dev/null
verify "$P" 4 "$OUT/spans-priv-on.json" || fail "privacy-on: fi_verify"
scan "$P" "$OUT/scan-on.txt"
grep -E "^marker:" "$OUT/scan-on.txt" | grep -q "= 0$" && fail "opt-in: marker not stored" || ok "opt-in: marker stored"
grep -E "^(username|hostname|home|traceback|atline|stack):" "$OUT/scan-on.txt" | grep -qv "= 0$" && fail "opt-in: user/host/path/stack stored" || ok "opt-in: still no username, hostname, home path, stack frames"

# nokeys
P="$BASE-nokeys"; serve "$P" UNSET_KEYS=1 || fail "nokeys: workerd did not start"
r="$(ask 'Reply with the single word: pong')"; case "$r" in 200*) ok "nokeys: application status 200";; *) fail "nokeys: status $r";; esac
sleep 5; "$PY" tools/scan_columns.py "$P" | tee -a "$SUMMARY" | grep -q "project: absent" && ok "nokeys: nothing exported, no project created" || fail "nokeys: a project exists"

# dead end
P="$BASE-dead"; serve "$P" FI_BASE_URL=http://127.0.0.1:9 || fail "deadend: workerd did not start"
r="$(ask 'Reply with the single word: pong')"; note "deadend request: $r"
case "$r" in 200*) ok "unreachable collector: request returned 200 ($(echo "$r" | cut -f2)s)";; *) fail "deadend: status $r";; esac
stop_worker
note; [ "$FAILED" = 0 ] && note "E2E PASS" || note "E2E FAIL"
exit "$FAILED"
