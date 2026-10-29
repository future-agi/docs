#!/usr/bin/env bash
# Re-record tests/fixtures/*.json from a REAL aigw run against a local capture server (no Future AGI needed).
# usage: tests/record_fixtures.sh /path/to/aigw   (env: OPENAI_BASE_URL OPENAI_API_KEY CHAT_MODEL; optional EMB_BASE_URL EMB_API_KEY EMB_MODEL)
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; AIGW="${1:?aigw path}"; PY="${PYTHON:-python3}"; CHAT_MODEL="${CHAT_MODEL:-gpt-4o-mini}"
run_pass() { # run_pass <name> <capture-env...>  ; sends chat+legacy completion (+embeddings when EMB_*)
  local name="$1"; shift
  "$PY" "$HERE/tests/capture_otlp.py" 19999 "$HERE/tests/fixtures/$name.json" & local cap=$!
  sleep 1
  env FI_API_KEY=fixture-key FI_SECRET_KEY=fixture-secret FI_OTLP_ENDPOINT=http://127.0.0.1:19999 FI_PROJECT_NAME=fixture-project "$@" "$HERE/run_aigw.sh" "$AIGW" >/dev/null 2>&1 & local gw=$!
  for _ in $(seq 1 90); do nc -z 127.0.0.1 1975 2>/dev/null && break; sleep 1; done; sleep 2
  curl -s -m60 -o /dev/null -H 'Content-Type: application/json' -H 'agent-session-id: fixture-session' -H 'x-tenant-id: fixture-tenant' localhost:1975/v1/chat/completions -d "{\"model\":\"$CHAT_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"FIXTURE_PROMPT_MARKER\"}],\"max_tokens\":50}"
  curl -s -m60 -o /dev/null -H 'Content-Type: application/json' localhost:1975/v1/completions -d "{\"model\":\"$CHAT_MODEL\",\"prompt\":\"FIXTURE_PROMPT_MARKER\",\"max_tokens\":20}"
  curl -s -m60 -o /dev/null -H 'Content-Type: application/json' localhost:1975/v1/chat/completions -d '{"model":"no-such-model","messages":[{"role":"user","content":"x"}]}'
  sleep 8; pkill -f "[a]igw run"; pkill -f envoy-versions; sleep 2; kill $cap 2>/dev/null; wait $cap 2>/dev/null
}
run_pass content_off
run_pass content_on FI_CAPTURE_CONTENT=1
echo "fixtures written"
