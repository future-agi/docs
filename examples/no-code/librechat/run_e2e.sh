#!/usr/bin/env bash
# End-to-end test of the LibreChat -> Future AGI recipe: a real LibreChat (Docker image), the shipped
# collector config and a real Future AGI. Self-hosted Future AGI in Docker is needed for the stored-data
# checks (check_spans.py, scan_local_stack.py read its Postgres and ClickHouse containers).
#
# Required environment:
#   FI_API_KEY, FI_SECRET_KEY          Future AGI keys
#   TEST_LLM_BASE_URL, TEST_LLM_API_KEY, TEST_LLM_MODEL
#                                      any OpenAI-compatible endpoint the LibreChat container can reach
#                                      (for example http://host.docker.internal:<port>/v1)
# Optional:
#   FI_TRACES_URL     default http://host.docker.internal:4318/v1/traces (self-hosted collector)
#   FI_PROJECT_NAME   default librechat-e2e; the content-on leg uses <name>-content
#   LIBRECHAT_VERSION default v0.8.8      OTELCOL_VERSION default 0.162.0     MONGO_TAG default 8.0.20
#   RUN_DIR           where rendered env files and evidence go (default: a new temp dir)
#   KEEP=1            leave the stack running
#
# Legs: (1) content off: a tool turn, a tool that fails, a provider failure, then the stored spans are
# checked and every stored column is scanned for the prompt, the reply, the tool result, the user's
# name/email/username, this machine's host and user name and the Future AGI secret key; (2) content on:
# the same marker must appear; (3) collector stopped: chats still work.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${TEST_LLM_BASE_URL:?set TEST_LLM_BASE_URL}" "${TEST_LLM_API_KEY:?set TEST_LLM_API_KEY}" "${TEST_LLM_MODEL:?set TEST_LLM_MODEL}"
export FI_TRACES_URL="${FI_TRACES_URL:-http://host.docker.internal:4318/v1/traces}"
PROJECT="${FI_PROJECT_NAME:-librechat-e2e}"
export RUN_DIR="${RUN_DIR:-$(mktemp -d)}"
export LIBRECHAT_VERSION="${LIBRECHAT_VERSION:-v0.8.8}" OTELCOL_VERSION="${OTELCOL_VERSION:-0.162.0}"
export MONGO_TAG="${MONGO_TAG:-8.0.20}" LIBRECHAT_PORT="${LIBRECHAT_PORT:-13080}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-librechat-futureagi-e2e}"
EVIDENCE="$RUN_DIR/evidence"
BASE="http://127.0.0.1:${LIBRECHAT_PORT}"
COMPOSE=(docker-compose -f "$HERE/compose.test.yml")
docker compose version >/dev/null 2>&1 && COMPOSE=(docker compose -f "$HERE/compose.test.yml")
mkdir -p "$EVIDENCE"

RUN_ID="$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
MARK_OFF="LCOFF${RUN_ID}"          # in the prompt of the content-off leg
MARK_TOOL="Z-${RUN_ID}"            # order id: travels as a tool argument and comes back in the tool result
MARK_ON="LCON${RUN_ID}"            # in the prompt of the content-on leg
USER_NAME="Privacy Probe ${RUN_ID}"
USER_EMAIL="probe-${RUN_ID}@example.test"
USER_LOGIN="probe${RUN_ID}"
PASSWORD="Pw-${RUN_ID}-$(python3 -c 'import secrets; print(secrets.token_hex(6))')"

log() { printf '\n== %s\n' "$*"; }
teardown() {
  if [ "${KEEP:-0}" != 1 ]; then "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; fi
}
trap teardown EXIT

wait_health() {
  for _ in $(seq 1 90); do
    # /health answers before LibreChat accepts chats; /readyz waits for its startup checks.
    [ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/readyz")" = 200 ] && return 0
    sleep 2
  done
  echo "LibreChat did not become healthy"; return 1
}

chat() {  # chat <evidence-name> <model> <mcp|-> <text>
  local out="$EVIDENCE/turn-$1.json" mcp=()
  [ "$3" != "-" ] && mcp=(--mcp "$3")
  python3 -I "$HERE/drive_chat.py" --base "$BASE" --name "$USER_NAME" --username "$USER_LOGIN" \
    --email "$USER_EMAIL" --password "$PASSWORD" --model "$2" ${mcp[@]+"${mcp[@]}"} --text "$4" > "$out" || true
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(" ", sys.argv[2], "final=%s error=%s tools=%s" % (d.get("final"), d.get("error"), d.get("tool_calls")))' "$out" "$1"
}

expect_turn() {  # expect_turn <evidence-name> <python condition on d>
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if eval(sys.argv[2]) else 1)' \
    "$EVIDENCE/turn-$1.json" "$2" || { echo "  turn $1 did not match: $2"; exit 1; }
}

log "render env into $RUN_DIR"
python3 -I "$HERE/tools/render_env.py" "$RUN_DIR"

log "leg 1: content off (project $PROJECT)"
export FI_PROJECT_NAME="$PROJECT" FI_CAPTURE_CONTENT=false
"${COMPOSE[@]}" up -d --quiet-pull
wait_health
chat tool "$TEST_LLM_MODEL" order-tools "${MARK_OFF} What is the status of order ${MARK_TOOL}? Use the order tool."
chat tool-failure "$TEST_LLM_MODEL" order-tools "${MARK_OFF} Cancel order ${MARK_TOOL} with the cancel tool and tell me what happened."
chat provider-failure th8234-missing-model - "${MARK_OFF} hello"
expect_turn tool 'd["final"] and not d["error"] and any("get_order_status" in t for t in d["tool_calls"])'
expect_turn tool-failure 'd["final"] and any("cancel_order" in t for t in d["tool_calls"])'
expect_turn provider-failure 'd["error"]'
sleep 10  # agent-run spans are batched by LibreChat (about 5 s) and the collector (2 s)
python3 -I "$HERE/tools/check_spans.py" --project "$PROJECT" --model "$TEST_LLM_MODEL" --expect-error \
  --expect-backend --json "$EVIDENCE/check-content-off.json"
python3 -I "$HERE/tools/scan_local_stack.py" --project "$PROJECT" --keys "$EVIDENCE/keys-content-off.json" \
  --json "$EVIDENCE/scan-content-off.json" \
  --needle "prompt_marker=$MARK_OFF" --needle "tool_arg_and_result=$MARK_TOOL" --needle "tool_result=DemoPost" \
  --needle "reply_text=shipped" --needle "provider_error=unknown provider" \
  --needle "tool_error_text=cancellation service unavailable" \
  --needle "user_name=$USER_NAME" --needle "user_email=$USER_EMAIL" --needle "user_login=$USER_LOGIN" \
  --needle "host_name=$(hostname -s)" --needle "os_user=$(id -un)" --needle "local_path=$HERE" \
  --needle "fi_secret=$FI_SECRET_KEY" --needle "fi_key=$FI_API_KEY"

log "leg 2: content on (project ${PROJECT}-content)"
export FI_PROJECT_NAME="${PROJECT}-content" FI_CAPTURE_CONTENT=true
"${COMPOSE[@]}" up -d --quiet-pull futureagi-otelcol
sleep 3
chat content-on "$TEST_LLM_MODEL" order-tools "${MARK_ON} What is the status of order ${MARK_TOOL}? Use the order tool."
expect_turn content-on 'd["final"] and not d["error"]'
python3 -I "$HERE/tools/check_spans.py" --project "${PROJECT}-content" --model "$TEST_LLM_MODEL" \
  --json "$EVIDENCE/check-content-on.json"
python3 -I "$HERE/tools/scan_local_stack.py" --project "${PROJECT}-content" --expect-found \
  --json "$EVIDENCE/scan-content-on.json" --needle "prompt_marker=$MARK_ON" --needle "tool_result=DemoPost"
python3 -I "$HERE/tools/scan_local_stack.py" --project "${PROJECT}-content" \
  --json "$EVIDENCE/scan-content-on-secrets.json" --needle "fi_secret=$FI_SECRET_KEY" \
  --needle "host_name=$(hostname -s)" --needle "os_user=$(id -un)"

log "leg 3: collector stopped, chats keep working"
"${COMPOSE[@]}" stop futureagi-otelcol >/dev/null
chat collector-down "$TEST_LLM_MODEL" - "Reply with the single word ok."
expect_turn collector-down 'd["final"] and not d["error"]'
echo "  chat completed with the collector down"

log "PASS. Evidence in $EVIDENCE"
