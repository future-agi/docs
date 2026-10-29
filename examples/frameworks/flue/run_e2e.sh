#!/usr/bin/env bash
# End-to-end run of the Flue -> Future AGI recipe with the real Flue CLI and
# runtime and a real model. Phases (each a fresh process):
#   off     `flue run`, content off (the recipe's default): one tool call, then a
#           tool failure
#   model   `flue run` with a wrong model API key (checks the chat span ERROR)
#   on      FI_CAPTURE_CONTENT=1 into project "<name>-optin": tool call + failure
#   server  `vite build`, `node dist/server.mjs`, one message, SIGTERM right
#           after it settles (checks the flush on shutdown)
#   script  a standalone start()/init() script that ends when its event loop drains
#   down    the exporter cannot reach Future AGI: the workflow must still work
# A local recorder sits in front of Future AGI and forwards every request
# unchanged, so the script can check the bytes on the wire. Every phase uses a
# fresh random marker in the prompt. OTEL_BSP_SCHEDULE_DELAY is set so high that
# only the shutdown flush (not the batch timer) can deliver the spans.
#
# Required: FI_API_KEY, FI_SECRET_KEY, MODEL_BASE_URL, MODEL_API_KEY, MODEL_ID
# Optional: FI_BASE_URL (default https://api.futureagi.com),
#           FI_PROJECT_NAME (default flue-e2e), FI_OPTIN_PROJECT_NAME
#           (default <FI_PROJECT_NAME>-optin), RECORDER_PORT (4331),
#           SERVER_PORT (3731), OUT (./evidence)
set -euo pipefail
cd "$(dirname "$0")"

: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${MODEL_BASE_URL:?set MODEL_BASE_URL}" "${MODEL_API_KEY:?set MODEL_API_KEY}" "${MODEL_ID:?set MODEL_ID}"
FI_UPSTREAM="${FI_BASE_URL:-https://api.futureagi.com}"
PROJECT="${FI_PROJECT_NAME:-flue-e2e}"
OPTIN_PROJECT="${FI_OPTIN_PROJECT_NAME:-${PROJECT}-optin}"
RECORDER_PORT="${RECORDER_PORT:-4331}"
SERVER_PORT="${SERVER_PORT:-3731}"
OUT="$(mkdir -p "${OUT:-./evidence}" && cd "${OUT:-./evidence}" && pwd)"
FLUE=./node_modules/.bin/flue
[ -x "$FLUE" ] || { echo "run npm install first" >&2; exit 2; }
export OTEL_BSP_SCHEDULE_DELAY=600000

pids=()
cleanup() { for p in "${pids[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

new_marker() { echo "$1$(node -e 'process.stdout.write(require("node:crypto").randomBytes(5).toString("hex"))')"; }

# flue run <phase> <label> <message> [KEY=VALUE ...]: stdout is the --json envelope.
flue_run() {
  local phase="$1" label="$2" message="$3"; shift 3
  env FI_BASE_URL="http://127.0.0.1:${RECORDER_PORT}" "$@" \
    "$FLUE" run src/agents/weather.ts --json --message "$message" \
    >"$OUT/$phase.$label.json" 2>"$OUT/$phase.$label.log" || true
  node -e 'const t=require("node:fs").readFileSync(process.argv[1],"utf8").trim();const e=t?JSON.parse(t.split("\n").pop()):{};console.log(process.argv[2]+" "+process.argv[3]+": "+(e.outcome??"no envelope"))' "$OUT/$phase.$label.json" "$phase" "$label"
}

node scripts/recorder.mjs --port "$RECORDER_PORT" --out "$OUT/wire" --forward "$FI_UPSTREAM" >"$OUT/recorder.log" 2>&1 &
pids+=("$!")
sleep 1

# What must never be exported, whatever the mode.
node -e 'const os=require("node:os");console.log(JSON.stringify({hostname:os.hostname(),user:os.userInfo().username,home:os.homedir(),cwd:process.cwd()}))' >"$OUT/identity.json"

# Phase off: content capture off (the recipe's default).
OFF=$(new_marker FLUEOFF)
flue_run off ok "Use get_weather for the city \"Paris $OFF\" and repeat the city name exactly in your answer." FI_PROJECT_NAME="$PROJECT"
flue_run off toolerr "Use get_weather for the city \"Atlantis $OFF\". If the tool fails, say so in one sentence." FI_PROJECT_NAME="$PROJECT"

# Phase model: a wrong model key, so the chat call fails.
ERR=$(new_marker FLUEERR)
flue_run model err "Use get_weather for the city \"Lisbon $ERR\"." FI_PROJECT_NAME="$PROJECT" MODEL_API_KEY=bad-key

# Phase on: the documented opt-in.
ON=$(new_marker FLUEON)
flue_run on ok "Use get_weather for the city \"Rome $ON\" and repeat the city name exactly in your answer." FI_PROJECT_NAME="$OPTIN_PROJECT" FI_CAPTURE_CONTENT=1
flue_run on toolerr "Use get_weather for the city \"Atlantis $ON\". If the tool fails, say so in one sentence." FI_PROJECT_NAME="$OPTIN_PROJECT" FI_CAPTURE_CONTENT=1

# Phase server: the built server, stopped with SIGTERM right after the message settles.
SRV=$(new_marker FLUESRV)
./node_modules/.bin/vite build >"$OUT/server.build.log" 2>&1
env FI_BASE_URL="http://127.0.0.1:${RECORDER_PORT}" FI_PROJECT_NAME="$PROJECT" PORT="$SERVER_PORT" node dist/server.mjs >"$OUT/server.log" 2>&1 &
SERVER_PID=$!
pids+=("$SERVER_PID")
for _ in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:${SERVER_PORT}/" && break; sleep 0.5; done
node scripts/invoke.mjs --url "http://127.0.0.1:${SERVER_PORT}" "Use get_weather for the city \"Oslo $SRV\" and repeat the city name exactly in your answer." >"$OUT/server.ok.json"
echo "server ok: $(cat "$OUT/server.ok.json" | head -c 160)"
kill -TERM "$SERVER_PID"
for _ in $(seq 1 30); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 0.5; done

# Phase script: a standalone workflow that ends when its event loop drains.
SCR=$(new_marker FLUESCR)
env FI_BASE_URL="http://127.0.0.1:${RECORDER_PORT}" FI_PROJECT_NAME="$PROJECT" \
  node scripts/ask.ts "Use get_weather for the city \"Lima $SCR\" and repeat the city name exactly in your answer." >"$OUT/script.ok.json" 2>"$OUT/script.ok.log" || true
echo "script ok: $(head -c 160 "$OUT/script.ok.json")"

# Phase down: nothing listens at the exporter URL. The workflow must still finish.
DWN=$(new_marker FLUEDWN)
start=$(node -e 'process.stdout.write(String(Date.now()))')
set +e
env FI_BASE_URL="http://127.0.0.1:9" FI_PROJECT_NAME="$PROJECT" \
  "$FLUE" run src/agents/weather.ts --json --message "Use get_weather for the city \"Cairo $DWN\" and repeat the city name exactly in your answer." \
  >"$OUT/down.ok.json" 2>"$OUT/down.ok.log"
down_exit=$?
set -e
end=$(node -e 'process.stdout.write(String(Date.now()))')
printf '{"exit":%s,"elapsedMs":%s}\n' "$down_exit" "$((end - start))" >"$OUT/down.exit.json"
echo "down: exit=$down_exit elapsed=$((end - start))ms"

sleep 2
printf '{"project":"%s","optinProject":"%s","off":"%s","err":"%s","on":"%s","server":"%s","script":"%s","down":"%s"}\n' "$PROJECT" "$OPTIN_PROJECT" "$OFF" "$ERR" "$ON" "$SRV" "$SCR" "$DWN" >"$OUT/markers.json"
node scripts/check_wire.mjs "$OUT"
