#!/usr/bin/env bash
# Start the standalone Envoy AI Gateway CLI (aigw) exporting traces to Future AGI.
# Mirrors the page: the same OTEL_* variables go on extProc.extraEnvVars in Helm.
# usage: ./run_aigw.sh [path-to-aigw]   (needs FI_API_KEY FI_SECRET_KEY OPENAI_API_KEY in env or .env)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/.env" ] && set -a && . "$HERE/.env" && set +a
AIGW="${1:-aigw}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
FI_OTLP_ENDPOINT="${FI_OTLP_ENDPOINT:-http://127.0.0.1:4318}"
FI_PROJECT_NAME="${FI_PROJECT_NAME-envoy-ai-gateway}"   # set FI_PROJECT_NAME= (empty) to test the missing-project case

# --- Future AGI export (traces only) ---
export OTEL_EXPORTER_OTLP_ENDPOINT="$FI_OTLP_ENDPOINT"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_HEADERS="X-Api-Key=${FI_API_KEY},X-Secret-Key=${FI_SECRET_KEY}"
[ -n "$FI_PROJECT_NAME" ] && export OTEL_RESOURCE_ATTRIBUTES="project_name=${FI_PROJECT_NAME},project_type=observe"
export OTEL_METRICS_EXPORTER="none"   # collector accepts traces only
export OTEL_LOGS_EXPORTER="none"      # aigw auto-wires gRPC OTLP access logs when an endpoint is set; turn off
# --- Privacy: content OFF unless you opt in with FI_CAPTURE_CONTENT=1 ---
# Envoy AI Gateway itself captures full prompts/responses by default; this recipe turns that off.
if [ "${FI_CAPTURE_CONTENT:-0}" = "1" ]; then
  export OPENINFERENCE_HIDE_INPUTS=false OPENINFERENCE_HIDE_OUTPUTS=false
  export OPENINFERENCE_HIDE_EMBEDDINGS_TEXT=false OPENINFERENCE_HIDE_EMBEDDINGS_VECTORS=false
else
  export OPENINFERENCE_HIDE_INPUTS=true OPENINFERENCE_HIDE_OUTPUTS=true
  export OPENINFERENCE_HIDE_EMBEDDINGS_TEXT=true OPENINFERENCE_HIDE_EMBEDDINGS_VECTORS=true
fi
# --- Session mapping (default already agent-session-id:session.id on spans) ---
# export OTEL_AIGW_SPAN_REQUEST_HEADER_ATTRIBUTES="agent-session-id:session.id,x-tenant-id:tenant.id"

if [ -n "${AIGW_CONFIG:-}" ]; then exec "$AIGW" run "$AIGW_CONFIG"; else exec "$AIGW" run; fi
