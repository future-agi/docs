#!/usr/bin/env bash
# Re-capture the protobuf fixtures from a REAL Kong gateway (not needed to run the tests).
# Kong exports to a local sink (capture_server.py) instead of Future AGI; the raw OTLP bodies are saved.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
: "${UPSTREAM_API_KEY:?}"
export UPSTREAM_MODEL="${UPSTREAM_MODEL:-gpt-6-luna}"
export UPSTREAM_CHAT_URL="${UPSTREAM_CHAT_URL:-http://host.docker.internal:8317/v1/chat/completions}"
export FI_TRACES_ENDPOINT="http://host.docker.internal:18318/v1/traces"
export FI_API_KEY=placeholder-key FI_SECRET_KEY=placeholder-secret FI_PROJECT_NAME=kong-fixture-project
OUT="$EVID/captured"; rm -rf "$OUT"; mkdir -p "$OUT"
python3 "$HERE/capture_server.py" --out-dir "$OUT" & SINK=$!
trap 'kill $SINK 2>/dev/null; stop_kong' EXIT
for mode in statistics-only with-payloads; do
  [ "$mode" = with-payloads ] && export LOG_PAYLOADS=true || export LOG_PAYLOADS=false
  render "$EVID/kong.capture.yml"; start_kong "$EVID/kong.capture.yml"
  chat "Reply with the single word ok. FIXTURE-PROMPT-MARKER" "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01" | tail -1
  sleep 6
  n=$(ls "$OUT"/*.pb | wc -l | tr -d ' ')
  echo "$mode: captured bodies so far: $n"
  cp "$(ls "$OUT"/*.pb | tail -1)" "$HERE/fixtures/kong-${KONG_IMAGE##*:}-$mode.pb"
done
