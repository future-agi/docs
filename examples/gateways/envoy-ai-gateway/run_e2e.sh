#!/usr/bin/env bash
# End-to-end: real aigw -> real Future AGI collector. Phases: default (content off), opt-in,
# failure (unknown model + bad collector key + missing project_name), embeddings (optional backend).
# usage: ./run_e2e.sh /path/to/aigw
# env:   FI_API_KEY FI_SECRET_KEY FI_OTLP_ENDPOINT FI_PROJECT_NAME OPENAI_BASE_URL OPENAI_API_KEY CHAT_MODEL
#        EMB_BASE_URL EMB_API_KEY EMB_MODEL   (optional, for the embeddings phase)
#        LOCAL_STACK=1 -> also run fi_verify.py (FI_VERIFY=/path/fi_verify.py) and tests/scan_local_stack.py
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; AIGW="${1:?path to aigw}"
OUT="${E2E_OUT:-$HERE/.e2e-out}"; mkdir -p "$OUT"
CHAT_MODEL="${CHAT_MODEL:-gpt-4o-mini}"; PORT=1975
STAMP="$(date +%s)"; M_OFF="ENVOYOFF${STAMP}"; M_ON="ENVOYON${STAMP}"; M_SESS="sess-envoy-${STAMP}"
echo "$M_OFF" > "$OUT/marker_off"; echo "$M_ON" > "$OUT/marker_on"; echo "$M_SESS" > "$OUT/session"

start() { # start <label> [VAR=value ...]  (extra env for run_aigw.sh)
  local label="$1"; shift
  stop; env "$@" "$HERE/run_aigw.sh" "$AIGW" > "$OUT/aigw-$label.log" 2>&1 &
  for _ in $(seq 1 90); do nc -z 127.0.0.1 $PORT 2>/dev/null && curl -fs -m1 localhost:1064/health >/dev/null 2>&1 && { sleep 1; return 0; }; sleep 1; done
  echo "aigw did not become healthy ($label)"; tail -5 "$OUT/aigw-$label.log"; return 1
}
stop() { pkill -f "[a]igw run" 2>/dev/null; pkill -f "envoy-versions" 2>/dev/null; sleep 2; }
chat() { curl -s -m60 -o "$OUT/last.json" -w "%{http_code}" -H "Content-Type: application/json" "${@:2}" "localhost:$PORT/v1/chat/completions" -d "$1"; }
flush() { sleep 8; stop; }   # aigw flushes the batch span processor on shutdown; the sleep covers its 5 s schedule
fail=0; check() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1 (got $2, want $3)"; fail=1; fi; }

echo "== 1. default: content OFF, session header, chat + legacy completions"
start off || exit 1
check "chat 200" "$(chat "{\"model\":\"$CHAT_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with one word. $M_OFF\"}],\"max_tokens\":50}" -H "agent-session-id: $M_SESS")" 200
check "legacy completion 200" "$(curl -s -m60 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' localhost:$PORT/v1/completions -d "{\"model\":\"$CHAT_MODEL\",\"prompt\":\"Say hi $M_OFF\",\"max_tokens\":20}")" 200
flush

echo "== 2. opt-in: FI_CAPTURE_CONTENT=1"
start on FI_CAPTURE_CONTENT=1 || exit 1
check "chat 200 (opt-in)" "$(chat "{\"model\":\"$CHAT_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with one word. $M_ON\"}],\"max_tokens\":50}")" 200
flush

echo "== 3a. failure: unknown model -> ERROR span (content off)"
start fail || exit 1
code="$(chat "{\"model\":\"no-such-model-$STAMP\",\"messages\":[{\"role\":\"user\",\"content\":\"x\"}]}")"; echo "gateway returned $code"
flush

if [ -n "${EMB_BASE_URL:-}" ]; then
  echo "== 4. embeddings (content off; backend $EMB_MODEL)"
  start emb OPENAI_BASE_URL="$EMB_BASE_URL" OPENAI_API_KEY="${EMB_API_KEY:-}" || exit 1
  check "embeddings 200" "$(curl -s -m60 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' localhost:$PORT/v1/embeddings -d "{\"model\":\"$EMB_MODEL\",\"input\":\"embedding text $M_OFF\"}")" 200
  flush
fi

echo "== 3b. wrong collector secret: user request still succeeds, export 401 is logged"
start badkey FI_SECRET_KEY=wrong || exit 1
check "chat 200 despite bad export key" "$(chat "{\"model\":\"$CHAT_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"badkey\"}],\"max_tokens\":20}")" 200
flush; grep -h "traces export" "$OUT/aigw-badkey.log" | sed -E 's/(ey=)[^ ,"]+/\1***/g' | head -2

echo "== 3c. project_name missing: collector rejects the batch"
start noproj FI_PROJECT_NAME= || exit 1
check "chat 200 without project" "$(chat "{\"model\":\"$CHAT_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"noproj\"}],\"max_tokens\":20}")" 200
flush; grep -h "traces export" "$OUT/aigw-noproj.log" | head -2

if [ "${LOCAL_STACK:-0}" = "1" ]; then
  echo "== verify against local stack"
  python3 "${FI_VERIFY:?path to fi_verify.py}" --project "$FI_PROJECT_NAME" --wait 120 --min-spans 3 --expect-type llm --json "$OUT/spans.json" || fail=1
  python3 "$HERE/tests/scan_local_stack.py" "$FI_PROJECT_NAME" "$M_OFF"   # must be absent -> exit 0
  echo "-- opt-in marker must be PRESENT (scanner exit 1 expected):"
  python3 "$HERE/tests/scan_local_stack.py" "$FI_PROJECT_NAME" "$M_ON" && { echo "FAIL opt-in content not found"; fail=1; } || echo "PASS opt-in marker present"
fi
stop; exit $fail
