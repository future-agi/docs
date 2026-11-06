#!/usr/bin/env bash
# End-to-end test of the LobeHub (LobeChat) -> Future AGI recipe: a real LobeHub server (Docker image, in
# Gateway Mode as LobeHub's own Docker Compose deploy runs it), the shipped collector config and a real
# Future AGI. Self-hosted Future AGI in Docker is needed for the stored-data checks (check_spans.py and
# scan_local_stack.py read its Postgres and ClickHouse containers).
#
# Required environment:
#   FI_API_KEY, FI_SECRET_KEY          Future AGI keys
#   TEST_LLM_BASE_URL, TEST_LLM_API_KEY, TEST_LLM_MODEL
#                                      any OpenAI-compatible endpoint the LobeHub container can reach
#                                      (for example http://host.docker.internal:<port>/v1)
# Optional:
#   FI_TRACES_URL     default http://host.docker.internal:4318/v1/traces (self-hosted collector)
#   FI_PROJECT_NAME   default lobehub-e2e; the content-on leg uses <name>-content
#   LOBEHUB_VERSION   default 2.2.19 (Docker tag of lobehub/lobehub)
#   PYTHON            a Python with requirements-test.txt installed (default python3)
#   ORDER_TOOLS_HOST  bind address of the test MCP server (default 127.0.0.1; on Linux Docker use 0.0.0.0
#                     so host.docker.internal reaches it)
#   RUN_DIR           where secrets and evidence go (default: a new temp dir)
#   KEEP=1            leave the stack running
#
# Legs: (1) content off: a tool turn, a tool that fails, a provider failure; the stored spans are checked
# and every stored column is scanned for the prompt marker, the order id, the tool result, the agent
# description, the provider error text, the test user's email, this machine's host and user name, the
# example's local path and the Future AGI keys; (2) content on: the agent description and LobeHub's own
# error text must appear, the keys and host details still must not; (3) collector stopped: runs still work.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${TEST_LLM_BASE_URL:?set TEST_LLM_BASE_URL}" "${TEST_LLM_API_KEY:?set TEST_LLM_API_KEY}" "${TEST_LLM_MODEL:?set TEST_LLM_MODEL}"
export FI_API_KEY FI_SECRET_KEY TEST_LLM_BASE_URL TEST_LLM_API_KEY TEST_LLM_MODEL
export FI_TRACES_URL="${FI_TRACES_URL:-http://host.docker.internal:4318/v1/traces}"
PROJECT="${FI_PROJECT_NAME:-lobehub-e2e}"
PY="${PYTHON:-python3}"
export RUN_DIR="${RUN_DIR:-$(mktemp -d)}"
export LOBEHUB_VERSION="${LOBEHUB_VERSION:-2.2.19}"
export COMPOSE_PROJECT="${COMPOSE_PROJECT:-lobehub-futureagi-e2e}"
export LOBE_PORT="${LOBE_PORT:-3210}" AGENT_GATEWAY_PORT="${AGENT_GATEWAY_PORT:-8787}"
export OTELCOL_CONFIG="$HERE/otelcol/otelcol.yaml"
MCP_PORT="${MCP_PORT:-8790}"
EVIDENCE="$RUN_DIR/evidence"
BASE="http://localhost:${LOBE_PORT}"
COMPOSE=(docker-compose -f "$HERE/compose.test.yml")
docker compose version >/dev/null 2>&1 && COMPOSE=(docker compose -f "$HERE/compose.test.yml")
mkdir -p "$EVIDENCE"

RUN_ID="$("$PY" -c 'import secrets; print(secrets.token_hex(4).upper())')"
MARK_OFF="LOBEOFF${RUN_ID}"        # prompts, order id and agent description of the content-off leg
MARK_ON="LOBEON${RUN_ID}"          # the same for the content-on leg

log() { printf '\n== %s\n' "$*"; }
MCP_PID=""
teardown() {
  [ -n "$MCP_PID" ] && kill "$MCP_PID" 2>/dev/null || true
  if [ "${KEEP:-0}" != 1 ]; then "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; fi
}
trap teardown EXIT

log "secrets for the test stack (LobeHub's setup.sh generates the same set)"
umask 077
JWKS="$(docker run --rm --entrypoint /bin/node "lobehub/lobehub:${LOBEHUB_VERSION}" -e 'const c=require("crypto");const {privateKey,publicKey}=c.generateKeyPairSync("rsa",{modulusLength:2048});const meta={alg:"RS256",kid:c.randomBytes(8).toString("hex"),use:"sig"};console.log(JSON.stringify({keys:[{...privateKey.export({format:"jwk"}),...meta}]}));console.log(JSON.stringify({keys:[{...publicKey.export({format:"jwk"}),...meta}]}))')"
export JWKS_KEY="${JWKS%%$'\n'*}" JWKS_PUBLIC_KEY="${JWKS#*$'\n'}"
export KEY_VAULTS_SECRET="$(openssl rand -base64 32)" AUTH_SECRET="$(openssl rand -base64 32)"
export GATEWAY_SERVICE_TOKEN="$(openssl rand -hex 32)" AGENT_EXEC_API_KEY="$(openssl rand -hex 24)"
export POSTGRES_PASSWORD="$(openssl rand -hex 12)"
umask 022

log "test MCP server on 127.0.0.1:${MCP_PORT}"
ORDER_TOOLS_HOST="${ORDER_TOOLS_HOST:-127.0.0.1}" ORDER_TOOLS_PORT="$MCP_PORT" "$PY" "$HERE/mcp/order_tools.py" >"$EVIDENCE/mcp.log" 2>&1 &
MCP_PID=$!

wait_ready() {
  for _ in $(seq 1 120); do
    case "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/")" in 2*|3*) return 0 ;; esac
    sleep 3
  done
  echo "LobeHub did not start"; return 1
}

drive() {  # drive <evidence-name> <marker> [turn ...]
  local name="$1" marker="$2"; shift 2
  "$PY" "$HERE/tools/drive_lobehub.py" --base-url "$BASE" --model "$TEST_LLM_MODEL" \
    --mcp-url "http://host.docker.internal:${MCP_PORT}/mcp" --marker "$marker" ${1+--only "$@"} \
    > "$EVIDENCE/runs-$name.json"
  "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); [print("  %-9s %-6s %s" % (r["turn"], r["status"], r["operation_id"])) for r in d["runs"]]' "$EVIDENCE/runs-$name.json"
}

expect_runs() {  # expect_runs <evidence-name> <python condition on runs (dict turn -> status)>
  "$PY" -c 'import json,sys; r={x["turn"]: x["status"] for x in json.load(open(sys.argv[1]))["runs"]}; sys.exit(0 if eval(sys.argv[2]) else 1)' \
    "$EVIDENCE/runs-$1.json" "$2" || { echo "  runs $1 did not match: $2"; exit 1; }
}

log "leg 1: content off (project $PROJECT), LobeHub ${LOBEHUB_VERSION}"
export FI_PROJECT_NAME="$PROJECT" FI_CAPTURE_CONTENT=false
SINCE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"${COMPOSE[@]}" up -d --quiet-pull
wait_ready
APP_HOST="$(docker inspect -f '{{.Config.Hostname}}' "${COMPOSE_PROJECT}-app")"  # LobeHub's host.name
drive off "$MARK_OFF"
expect_runs off 'r["tool"] == "done" and r["tool_fail"] == "done" and r["provider"] == "error"'
"$PY" "$HERE/tools/check_spans.py" --project "$PROJECT" --model "$TEST_LLM_MODEL" --expect-error \
  --since "$SINCE" --min-runs 3 --wait 180 --json "$EVIDENCE/check-content-off.json"
"$PY" "$HERE/tools/scan_local_stack.py" --project "$PROJECT" --keys "$EVIDENCE/keys-content-off.json" \
  --json "$EVIDENCE/scan-content-off.json" \
  --needle "prompt_marker=$MARK_OFF" --needle "order_id=ORD-$MARK_OFF" --needle "tool_result=ParcelCo" \
  --needle "tool_error_text=already shipped" --needle "agent_description=Order helper for tests" \
  --needle "provider_error=unknown provider" --needle "status_text=skill discovery requests failed" \
  --needle "user_email=@example.test" --needle "container_host=$APP_HOST" \
  --needle "host_name=$(hostname -s)" --needle "os_user=$(id -un)" --needle "local_path=$HERE" \
  --needle "fi_secret=$FI_SECRET_KEY" --needle "fi_key=$FI_API_KEY" \
  --needle "process_owner_key=process.owner" --needle "host_name_key=host.name" \
  --needle "node_path=/bin/node" --needle "server_path=/app/server.js"

log "leg 2: content on (project ${PROJECT}-content)"
export FI_PROJECT_NAME="${PROJECT}-content" FI_CAPTURE_CONTENT=true
"${COMPOSE[@]}" up -d --quiet-pull futureagi-otelcol
sleep 3
drive on "$MARK_ON" tool provider
expect_runs on 'r["tool"] == "done" and r["provider"] == "error"'
"$PY" "$HERE/tools/check_spans.py" --project "${PROJECT}-content" --model "$TEST_LLM_MODEL" --expect-error \
  --since "$SINCE" --min-runs 2 --wait 180 --json "$EVIDENCE/check-content-on.json"
"$PY" "$HERE/tools/scan_local_stack.py" --project "${PROJECT}-content" --expect-found \
  --json "$EVIDENCE/scan-content-on.json" --needle "agent_description=$MARK_ON-DESC" \
  --needle "status_text=skill discovery requests failed"
"$PY" "$HERE/tools/scan_local_stack.py" --project "${PROJECT}-content" \
  --json "$EVIDENCE/scan-content-on-secrets.json" --needle "prompt_never_exported=Ref $MARK_ON" \
  --needle "fi_secret=$FI_SECRET_KEY" --needle "host_name=$(hostname -s)" --needle "os_user=$(id -un)"

log "leg 3: collector stopped, agent runs keep working"
"${COMPOSE[@]}" stop futureagi-otelcol >/dev/null
drive down "${MARK_OFF}DOWN" tool
expect_runs down 'r["tool"] == "done"'
echo "  agent run completed with the collector down"

log "PASS. Evidence in $EVIDENCE"
