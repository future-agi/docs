#!/usr/bin/env bash
# End-to-end run of the eve -> Future AGI recipe with a real eve dev server and
# a real model. Three phases, each a fresh `eve dev` process:
#   off    content capture off (default): one tool call, one tool failure,
#          then SIGINT right after the last turn (checks the shutdown flush)
#   model  content off, wrong model API key (checks the chat span ERROR)
#   on     FI_CAPTURE_CONTENT=1, one tool call, project "<name>-optin"
# A local recorder sits in front of Future AGI and forwards every request
# unchanged, so the script can check the bytes on the wire. Each run uses a
# fresh random marker in the prompt.
#
# Required: FI_API_KEY, FI_SECRET_KEY, MODEL_BASE_URL, MODEL_API_KEY, MODEL_ID
# Optional: FI_BASE_URL (default https://api.futureagi.com),
#           FI_PROJECT_NAME (default eve-e2e), EVE_PORT (2410),
#           RECORDER_PORT (4329), OUT (./evidence)
set -euo pipefail
cd "$(dirname "$0")"

: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${MODEL_BASE_URL:?set MODEL_BASE_URL}" "${MODEL_API_KEY:?set MODEL_API_KEY}" "${MODEL_ID:?set MODEL_ID}"
FI_UPSTREAM="${FI_BASE_URL:-https://api.futureagi.com}"
PROJECT="${FI_PROJECT_NAME:-eve-e2e}"
EVE_PORT="${EVE_PORT:-2410}"
RECORDER_PORT="${RECORDER_PORT:-4329}"
OUT="$(mkdir -p "${OUT:-./evidence}" && cd "${OUT:-./evidence}" && pwd)"
EVE_BIN=./node_modules/.bin/eve
[ -x "$EVE_BIN" ] || { echo "run npm install first" >&2; exit 2; }

pids=()
cleanup() { for p in "${pids[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

new_marker() { echo "$1$(node -e 'process.stdout.write(require("node:crypto").randomBytes(5).toString("hex"))')"; }

start_eve() { # $1 phase name; the rest is extra env (KEY=VALUE ...)
  local phase="$1"; shift
  rm -rf .eve
  env FI_BASE_URL="http://127.0.0.1:${RECORDER_PORT}" "$@" \
    "$EVE_BIN" dev --no-ui --port "$EVE_PORT" --host 127.0.0.1 >"$OUT/$phase.eve.log" 2>&1 &
  EVE_PID=$!
  pids+=("$EVE_PID")
  for _ in $(seq 1 90); do
    if curl -s -o /dev/null "http://127.0.0.1:${EVE_PORT}/"; then return 0; fi
    sleep 1
  done
  echo "eve dev did not start; see $OUT/$phase.eve.log" >&2
  exit 1
}

stop_eve() { # SIGINT, as Ctrl+C would, then wait for the process to exit
  kill -INT "$EVE_PID" 2>/dev/null || true
  for _ in $(seq 1 30); do kill -0 "$EVE_PID" 2>/dev/null || return 0; sleep 1; done
  kill "$EVE_PID" 2>/dev/null || true
}

ask() { # $1 phase, $2 label, $3 message
  node scripts/invoke.mjs --url "http://127.0.0.1:${EVE_PORT}" "$3" | tee "$OUT/$1.$2.json"
}

node scripts/recorder.mjs --port "$RECORDER_PORT" --out "$OUT/wire" --forward "$FI_UPSTREAM" >"$OUT/recorder.log" 2>&1 &
pids+=("$!")
sleep 1

# Phase off: content capture off (the recipe's default).
OFF=$(new_marker EVEOFF)
start_eve off FI_PROJECT_NAME="$PROJECT" FI_CAPTURE_CONTENT=
ask off ok "Use get_weather for the city \"Paris $OFF\" and repeat the city name exactly in your answer."
ask off toolerr "Use get_weather for the city \"Atlantis $OFF\". If the tool fails, say so in one sentence."
stop_eve # immediately: the spans of the last turn must still be exported on shutdown

# Phase model: a wrong model key, so the chat call fails.
ERR=$(new_marker EVEERR)
start_eve model FI_PROJECT_NAME="$PROJECT" FI_CAPTURE_CONTENT= MODEL_API_KEY=invalid-key-for-e2e
ask model err "Use get_weather for the city \"Lisbon $ERR\"." || true
stop_eve

# Phase on: the documented opt-in.
ON=$(new_marker EVEON)
start_eve on FI_PROJECT_NAME="${PROJECT}-optin" FI_CAPTURE_CONTENT=1
ask on ok "Use get_weather for the city \"Rome $ON\" and repeat the city name exactly in your answer."
stop_eve

sleep 2
printf '{"project":"%s","off":"%s","model":"%s","on":"%s"}\n' "$PROJECT" "$OFF" "$ERR" "$ON" >"$OUT/markers.json"
node scripts/check_wire.mjs "$OUT"
