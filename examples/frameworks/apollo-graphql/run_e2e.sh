#!/usr/bin/env bash
# End-to-end run of the Apollo Server 4 recipe against a Future AGI you can read back (self-hosted).
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   VERIFY=/path/to/fi_verify.py ./run_e2e.sh [traces|privacy|optin|all]
#
# Everything is real: Apollo Server 4.13.0 (server.mjs, started exactly as the page says), the
# OpenTelemetry GraphQL + HTTP instrumentations, the OTLP/HTTP exporter and Future AGI. No model
# is involved. Output: ./evidence (never commit it).
#
#   traces   a normal query, a query with a resolver child span, a wide query, a throwing query, a partial one
#   privacy  default (content off): unique markers in a variable value, an inline literal and an error
#            text must be absent from every stored column (scan_local_stack.py)
#   optin    FI_APOLLO_CAPTURE_CONTENT=true: the masked query text and the error message appear
#
# Environment: FI_API_KEY FI_SECRET_KEY FI_BASE_URL (required) VERIFY (fi_verify.py, optional)
#   PY [python3]  PORT_BASE [4400]  FI_PROJECT_PREFIX [apollo-e2e]  RUN_ID [empty = no suffix]  OUT [./evidence]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PY:-python3}"
OUT="${OUT:-$PWD/evidence}"; mkdir -p "$OUT"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}"
PREFIX="${FI_PROJECT_PREFIX:-apollo-e2e}${RUN_ID:+-$RUN_ID}"
PORT="${PORT_BASE:-4400}"

gql() { # gql <url> <json-body>
  curl -sS -X POST "$1" -H 'content-type: application/json' -d "$2"; echo
}

run_server() { # run_server <project> [extra env...]; sends the queries, then SIGTERM (flushes)
  local project="$1"; shift
  ( cd "$HERE" && exec env "$@" FI_PROJECT_NAME="$project" PORT="$PORT" node server.mjs > "$OUT/$project.server.log" 2>&1 ) &
  echo $! > "$OUT/$project.pid"
  local pid; pid="$(cat "$OUT/$project.pid")"
  for _ in $(seq 1 50); do grep -q "ready at" "$OUT/$project.server.log" 2>/dev/null && break; sleep 0.2; done
  local url="http://127.0.0.1:$PORT/"
  gql "$url" '{"query":"query Hello { hello }","operationName":"Hello"}' > "$OUT/$project.hello.json"
  gql "$url" '{"query":"query Profile($id: ID!) { profile(id: $id) { id name email } }","operationName":"Profile","variables":{"id":"'"${MARKER_VARIABLE:-var-1}"'"}}' > "$OUT/$project.profile.json"
  gql "$url" '{"query":"query Wide { wide { f01 f02 f03 f04 f05 f06 f07 f08 f09 f10 f11 f12 f13 f14 f15 f16 f17 f18 f19 f20 } }","operationName":"Wide"}' > /dev/null
  gql "$url" '{"query":"query Lit { profile(id: \"'"${MARKER_LITERAL:-lit-1}"'\") { id } }","operationName":"Lit"}' > /dev/null
  gql "$url" '{"query":"query Fail($why: String) { fail(reason: $why) }","operationName":"Fail","variables":{"why":"'"${MARKER_ERROR:-err-1}"'"}}' > "$OUT/$project.fail.json"
  gql "$url" '{"query":"query Partial { partial { ok bad } }","operationName":"Partial"}' > /dev/null
  kill -TERM "$pid"; for _ in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
  if kill -0 "$pid" 2>/dev/null; then echo "server did not exit on SIGTERM" >&2; kill -9 "$pid"; return 1; fi
  PORT=$((PORT + 1))
}

verify() { # verify <project> [fi_verify args]
  local project="$1"; shift
  [ -n "${VERIFY:-}" ] && "$PY" "$VERIFY" --project "$project" --wait 120 --min-spans 6 --json "$OUT/$project.spans.json" "$@" | tee "$OUT/$project.verify.txt"
}

if [[ "$MODE" == traces || "$MODE" == all ]]; then
  P="$PREFIX-traces"
  MARKER_VARIABLE=var-1 run_server "$P" FI_API_KEY="$FI_API_KEY" FI_SECRET_KEY="$FI_SECRET_KEY" FI_BASE_URL="$FI_BASE_URL"
  verify "$P"
fi

if [[ "$MODE" == privacy || "$MODE" == optin || "$MODE" == all ]]; then
  SUFFIX="$(date +%H%M%S)$RANDOM"
  export MARKER_VARIABLE="MARKVAR$SUFFIX" MARKER_LITERAL="MARKLIT$SUFFIX" MARKER_ERROR="MARKERR$SUFFIX"
  NEEDLES=(--needle "$MARKER_VARIABLE" --needle "$MARKER_LITERAL" --needle "$MARKER_ERROR" --needle "secret-path.js" --needle "home=$HOME" --needle "user=$(id -un)" --needle "host=$(hostname)")
  if [[ "$MODE" == privacy || "$MODE" == all ]]; then
    P="$PREFIX-privacy"
    run_server "$P" FI_API_KEY="$FI_API_KEY" FI_SECRET_KEY="$FI_SECRET_KEY" FI_BASE_URL="$FI_BASE_URL"
    verify "$P"
    "$PY" "$HERE/tools/scan_local_stack.py" --project "$P" "${NEEDLES[@]}" | tee "$OUT/$P.scan.txt"
  fi
  if [[ "$MODE" == optin || "$MODE" == all ]]; then
    P="$PREFIX-optin"
    run_server "$P" FI_API_KEY="$FI_API_KEY" FI_SECRET_KEY="$FI_SECRET_KEY" FI_BASE_URL="$FI_BASE_URL" FI_APOLLO_CAPTURE_CONTENT=true
    verify "$P"
    # opt-in: the error message (with its marker) and the masked query text are stored; the variable
    # value and the inline literal never are.
    "$PY" "$HERE/tools/scan_local_stack.py" --project "$P" --needle "$MARKER_ERROR" --expect-found | tee "$OUT/$P.scan-error.txt"
    "$PY" "$HERE/tools/scan_local_stack.py" --project "$P" --needle "$MARKER_VARIABLE" --needle "$MARKER_LITERAL" --needle "stacktrace" | tee "$OUT/$P.scan-never.txt"
  fi
fi
echo "run_e2e: done ($MODE)"
